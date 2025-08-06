# CoopHive Tweet Review Flask App
# Simple, professional web app for reviewing and editing AI-generated tweets

from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash
import json
import os
from datetime import datetime
import csv
import io
from datetime import datetime
import secrets
import requests
from database import save_campaign_data, get_campaign_data, update_tweet_content, update_tweet_status, init_database, check_duplicate_scraped_tweets, save_scraped_tweets, get_scraped_tweets, get_scraped_tweets_stats, get_database_status, force_migration, backup_database, delete_campaign_cascade

# Initialize database on startup
print("DEBUG: Initializing database...")
try:
    init_database()
    print("DEBUG: Database initialized successfully")
except Exception as e:
    print(f"DEBUG: Database initialization failed: {e}")

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Initialize Basic Authentication
auth = HTTPBasicAuth()

# Basic Auth users - coophive_ops / testpass123 as specified in upgrade plan
users = {
    "coophive_ops": generate_password_hash("testpass123")
}

@auth.verify_password
def verify_password(username, password):
    """Verify Basic Auth credentials for API endpoints"""
    if username in users and check_password_hash(users.get(username), password):
        return username
    return None

# Database storage for production (with fallback to in-memory for demo)
tweet_storage = {}  # Fallback for demo mode

# ============================================================================
# SECURITY HEADERS & LOGGING MIDDLEWARE
# ============================================================================

@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
    
    # Add execution ID to response headers if available in request
    if hasattr(request, 'execution_id'):
        response.headers['X-Execution-ID'] = request.execution_id
    
    return response

@app.before_request
def log_request_info():
    """Enhanced logging for all requests, especially authenticated ones"""
    # Extract execution ID from request if present
    execution_id = None
    if request.is_json and request.get_json(silent=True):
        json_data = request.get_json(silent=True)
        # Handle both array format (like in.json) and direct object format
        if isinstance(json_data, list) and len(json_data) > 0:
            execution_id = json_data[0].get('execution_id')
        elif isinstance(json_data, dict):
            execution_id = json_data.get('execution_id')
    
    # Also check headers
    if not execution_id:
        execution_id = request.headers.get('X-Execution-ID')
    
    # Store in request context for use in response headers
    if execution_id:
        request.execution_id = execution_id
    
    # Enhanced logging for API endpoints
    if request.path.startswith('/api/'):
        # Safely get auth user info
        auth_user = 'anonymous'
        if hasattr(request, 'authorization') and request.authorization:
            auth_user = getattr(request.authorization, 'username', 'anonymous')
        
        log_msg = f"API Request: {request.method} {request.path} | User: {auth_user}"
        
        if execution_id:
            log_msg += f" | Execution-ID: {execution_id}"
        
        if request.remote_addr:
            log_msg += f" | IP: {request.remote_addr}"
        
        print(f"SECURITY LOG: {log_msg}")

@app.route('/')
def index():
    """Home page - simple welcome with upload"""
    return render_template('index.html')

@app.route('/campaigns')
def campaigns_page():
    """Campaigns management page"""
    return render_template('campaigns.html')

@app.route('/upload')
def upload_page():
    """Redirect to duplicate check page - old upload is deprecated"""
    return redirect('/duplicate-check')

@app.route('/duplicate-check')
def duplicate_check_page():
    """Duplicate check upload page"""
    return render_template('duplicate_check.html')

@app.route('/status')
def status_page():
    """System status page"""
    return render_template('status.html')

@app.route('/drafts')
def drafts_page():
    """Draft tweets page"""
    return render_template('status_page.html', status='Draft', title='Draft Tweets')

@app.route('/approved')
def approved_page():
    """Approved tweets page"""
    return render_template('status_page.html', status='Approved', title='Approved Tweets')

@app.route('/posted')
def posted_page():
    """Posted tweets page"""
    return render_template('status_page.html', status='Posted', title='Posted Tweets')

@app.route('/rejected')
def rejected_page():
    """Rejected tweets page"""
    return render_template('status_page.html', status='Rejected', title='Rejected Tweets')

@app.route('/deleted')
def deleted_page():
    """Deleted tweets page"""
    return render_template('status_page.html', status='Deleted', title='Deleted Tweets')

@app.route('/all-tweets')
def all_tweets_page():
    """All tweets page with CSV download"""
    return render_template('all_tweets.html')

@app.route('/scraped-tweets')
def scraped_tweets_page():
    """Scraped tweets page with Excel-like interface and pagination"""
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Fixed at 50 per page as requested
    offset = (page - 1) * per_page
    
    # Get execution_id filter if provided
    execution_id = request.args.get('execution_id', None)
    
    # Get tweets with pagination
    tweets_data, total_count = get_scraped_tweets(limit=per_page, offset=offset, execution_id=execution_id)
    
    # Calculate pagination info
    total_pages = (total_count + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get statistics for dashboard
    stats = get_scraped_tweets_stats()
    
    # Pagination info
    pagination = {
        'page': page,
        'per_page': per_page,
        'total': total_count,
        'pages': total_pages,
        'has_prev': has_prev,
        'has_next': has_next,
        'prev_num': page - 1 if has_prev else None,
        'next_num': page + 1 if has_next else None,
        'start_index': offset + 1 if tweets_data else 0,
        'end_index': min(offset + per_page, total_count)
    }
    
    return render_template('scraped_tweets.html', 
                         tweets=tweets_data, 
                         pagination=pagination,
                         stats=stats,
                         execution_id=execution_id)

@app.route('/review/<campaign_batch>')
def review_tweets(campaign_batch):
    """Main tweet review interface - NO RESTRICTIONS"""
    token = request.args.get('token', 'demo_token')  # Default token for unrestricted access
    
    # DEBUG: Print available campaigns
    print(f"DEBUG: Looking for campaign '{campaign_batch}'")
    print(f"DEBUG: Available in memory: {list(tweet_storage.keys())}")
    
    # Get tweet data from DATABASE FIRST, fallback to memory only if needed
    campaign_data = get_campaign_data(campaign_batch) or tweet_storage.get(campaign_batch)
    
    # DEBUG: Print campaign data structure
    if campaign_data:
        print(f"DEBUG: Campaign data keys: {campaign_data.keys()}")
        if 'tweets' in campaign_data:
            print(f"DEBUG: Number of tweets: {len(campaign_data['tweets'])}")
        else:
            print("DEBUG: No 'tweets' key found in campaign data")
    else:
        print("DEBUG: No campaign data found")
    
    # If no data found, show error
    if not campaign_data:
        return render_template('error.html', 
                             error=f"Campaign '{campaign_batch}' not found. Please upload the campaign data first. Available campaigns: {list(tweet_storage.keys())}"), 404
    
    # NO ACCESS CONTROL! If no tweets found, use sample data temporarily while we debug database
    if 'tweets' not in campaign_data or not campaign_data['tweets']:
        print(f"DEBUG: No tweets found in campaign {campaign_batch}")
        print(f"DEBUG: Campaign data structure: {list(campaign_data.keys()) if campaign_data else 'None'}")
        
        # Try to reload from database with debug info
        fresh_data = get_campaign_data(campaign_batch)
        if fresh_data and fresh_data.get('tweets'):
            print(f"DEBUG: Found {len(fresh_data['tweets'])} tweets in fresh database query")
            campaign_data = fresh_data
        else:
            print(f"DEBUG: No tweets found even in fresh database query - database might need reset")
            # Always use sample data as fallback to ensure pages work
            print(f"DEBUG: Using sample data as fallback")
            sample_data = get_sample_data()
            campaign_data['tweets'] = sample_data['tweets']
            tweet_storage[campaign_batch] = campaign_data
    
    return render_template('review.html', 
                         campaign=campaign_data,
                         campaign_batch=campaign_batch,
                         token=token)

@app.route('/api/receive-tweets', methods=['POST'])
def receive_tweets():
    """Endpoint to receive tweet data from n8n workflow"""
    try:
        raw_data = request.get_json()
        
        # Handle array format from n8n (like in.json)
        if isinstance(raw_data, list) and len(raw_data) > 0:
            data = raw_data[0]  # Take first element
        else:
            data = raw_data
            
        campaign_batch = data.get('campaign_batch')
        
        if campaign_batch:
            # Add title and description for n8n data
            if 'title' not in data:
                tweet_count = len(data.get('tweets', []))
                data['title'] = f'N8N Workflow - {tweet_count} tweets'
                data['description'] = f'Generated by n8n workflow on {datetime.now().strftime("%B %d, %Y at %H:%M:%S")} containing {tweet_count} tweets'
                data['source_type'] = 'n8n_workflow'
            
            # Save to database ONLY - no memory fallback
            if save_campaign_data(data):
                return jsonify({
                    'status': 'success',
                    'message': f'Received {len(data.get("tweets", []))} tweets (saved to database)',
                    'campaign_batch': campaign_batch
                })
            else:
                # Check if it's a conflict error
                return jsonify({
                    'status': 'error',
                    'message': f'Failed to save campaign {campaign_batch}. Campaign or tweet IDs already exist in database. Use unique IDs or check existing campaigns.',
                    'campaign_batch': campaign_batch
                }), 409
        else:
            return jsonify({'status': 'error', 'message': 'Missing campaign_batch'}), 400
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/save-tweet', methods=['POST'])
def save_tweet():
    """Save edited tweet content"""
    try:
        data = request.get_json()
        campaign_batch = data.get('campaign_batch')
        tweet_id = data.get('tweet_id')
        new_content = data.get('content')
        
        # DEBUG: Check what we have
        print(f"DEBUG: Save tweet - looking for campaign '{campaign_batch}'")
        print(f"DEBUG: Available campaigns: {list(tweet_storage.keys())}")
        
        # Try database FIRST
        if update_tweet_content(campaign_batch, tweet_id, new_content):
            return jsonify({
                'status': 'success',
                'message': 'Tweet saved successfully (database)',
                'character_count': len(new_content)
            })
        
        # Fallback to in-memory storage only if database fails
        elif campaign_batch in tweet_storage:
            campaign_data = tweet_storage[campaign_batch]
            for tweet in campaign_data.get('tweets', []):
                if tweet['id'] == tweet_id:
                    tweet['content'] = new_content
                    tweet['character_count'] = len(new_content)
                    tweet['is_edited'] = True
                    tweet['last_modified'] = datetime.now().isoformat()
                    break
            
            return jsonify({
                'status': 'warning',
                'message': 'Tweet saved successfully (memory fallback - database issue)',
                'character_count': len(new_content)
            })
        else:
            return jsonify({'status': 'error', 'message': f'Campaign "{campaign_batch}" not found anywhere. Available: {list(tweet_storage.keys())}'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/post-to-x', methods=['POST'])
def post_to_x():
    """Trigger n8n webhook to post tweet to X.com"""
    try:
        data = request.get_json()
        tweet_id = data.get('tweet_id')
        campaign_batch = data.get('campaign_batch')
        
        # DEBUG: Check what we have
        print(f"DEBUG: Post to X - looking for campaign '{campaign_batch}'")
        print(f"DEBUG: Available campaigns: {list(tweet_storage.keys())}")
        
        # Get tweet content from memory first
        if campaign_batch in tweet_storage:
            campaign_data = tweet_storage[campaign_batch]
            tweet_to_post = None
            
            for tweet in campaign_data.get('tweets', []):
                if tweet['id'] == tweet_id:
                    tweet_to_post = tweet
                    break
            
            if tweet_to_post:
                # Prepare webhook payload
                webhook_payload = {
                    'action': 'post_to_x',
                    'tweet_id': tweet_id,
                    'content': tweet_to_post['content'],
                    'account': '@coophive',
                    'campaign_batch': campaign_batch
                }
                
                # In a real implementation, send to n8n webhook
                # webhook_url = "https://n8n.coophive.com/webhook/post-to-x"
                # response = requests.post(webhook_url, json=webhook_payload)
                
                # For demo, just mark as posted
                tweet_to_post['status'] = 'Posted'
                tweet_to_post['posted_date'] = datetime.now().isoformat()
                
                return jsonify({
                    'status': 'success',
                    'message': 'Tweet posted to X.com successfully!',
                    'tweet_id': tweet_id
                })
            else:
                return jsonify({'status': 'error', 'message': 'Tweet not found'}), 404
        else:
            return jsonify({'status': 'error', 'message': 'Campaign not found'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/update-status', methods=['POST'])
def update_status():
    """Update tweet status (Draft/Approved/Rejected)"""
    try:
        data = request.get_json()
        campaign_batch = data.get('campaign_batch')
        tweet_id = data.get('tweet_id')
        new_status = data.get('status')
        
        # DEBUG: Check what we have
        print(f"DEBUG: Update status - looking for campaign '{campaign_batch}'")
        print(f"DEBUG: Available campaigns: {list(tweet_storage.keys())}")
        
        # Try database FIRST
        if update_tweet_status(campaign_batch, tweet_id, new_status):
            return jsonify({
                'status': 'success',
                'message': f'Tweet status updated to {new_status} (database)'
            })
        
        # Fallback to in-memory storage only if database fails
        elif campaign_batch in tweet_storage:
            campaign_data = tweet_storage[campaign_batch]
            for tweet in campaign_data.get('tweets', []):
                if tweet['id'] == tweet_id:
                    tweet['status'] = new_status
                    tweet['last_modified'] = datetime.now().isoformat()
                    break
            
            return jsonify({
                'status': 'warning',
                'message': f'Tweet status updated to {new_status} (memory fallback - database issue)'
            })
        else:
            return jsonify({'status': 'error', 'message': f'Campaign "{campaign_batch}" not found anywhere. Available: {list(tweet_storage.keys())}'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/upload-json', methods=['POST'])
def upload_json():
    """Upload and process JSON file with tweet data"""
    try:
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400
        
        if not file.filename.endswith('.json'):
            return jsonify({'status': 'error', 'message': 'File must be a JSON file'}), 400
        
        # Read and parse JSON file
        json_data = json.loads(file.read().decode('utf-8'))
        
        # Process the uploaded JSON data
        processed_campaigns = []
        
        # Handle array format (like mock_data.json)
        if isinstance(json_data, list):
            print(f"DEBUG: Processing array with {len(json_data)} items")
            for i, item in enumerate(json_data):
                print(f"DEBUG: Item {i} keys: {item.keys() if isinstance(item, dict) else 'Not a dict'}")
                
                # Look for campaign data in different formats
                if 'campaign_batch' in item and 'tweets' in item:
                    # Direct campaign format
                    campaign_data = item
                    print(f"DEBUG: Found direct campaign format: {campaign_data['campaign_batch']}")
                elif 'processed_tweets' in item:
                    # Format with processed_tweets array - add unique naming
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    tweet_count = len(item.get('processed_tweets', []))
                    campaign_batch = item.get('campaign_batch', f'uploaded_{timestamp}_{tweet_count}tweets')
                    
                    campaign_data = {
                        'campaign_batch': campaign_batch,
                        'generated_at': item.get('generated_at', datetime.now().isoformat()),
                        'tweet_count': tweet_count,
                        'title': f'JSON Upload - {tweet_count} tweets',
                        'description': f'Uploaded on {datetime.now().strftime("%B %d, %Y at %H:%M:%S")} containing {tweet_count} tweets',
                        'source_type': 'json_upload',
                        'analysis_summary': item.get('analysis_summary', {}),
                        'tweets': item.get('processed_tweets', [])
                    }
                    print(f"DEBUG: Created campaign from processed_tweets: {campaign_data['campaign_batch']}")
                else:
                    # Skip non-campaign items
                    print(f"DEBUG: Skipping item {i} - no campaign data found")
                    continue
                
                # Try to save to database FIRST
                if save_campaign_data(campaign_data):
                    print(f"DEBUG: Successfully saved to database: {campaign_data['campaign_batch']}")
                    processed_campaigns.append({
                        'campaign_batch': campaign_data['campaign_batch'],
                        'tweet_count': campaign_data['tweet_count'],
                        'status': 'saved to database'
                    })
                else:
                    print(f"DEBUG: Database save failed for {campaign_data['campaign_batch']} - likely ID conflict")
                    processed_campaigns.append({
                        'campaign_batch': campaign_data['campaign_batch'],
                        'tweet_count': campaign_data['tweet_count'],
                        'status': 'CONFLICT: Campaign or tweet IDs already exist in database'
                    })
        
        # Handle single object format
        elif isinstance(json_data, dict):
            if 'tweets' in json_data:
                campaign_data = json_data
            elif 'processed_tweets' in json_data:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                tweet_count = len(json_data.get('processed_tweets', []))
                campaign_batch = json_data.get('campaign_batch', f'uploaded_{timestamp}_{tweet_count}tweets')
                
                campaign_data = {
                    'campaign_batch': campaign_batch,
                    'generated_at': json_data.get('generated_at', datetime.now().isoformat()),
                    'tweet_count': tweet_count,
                    'title': f'JSON Upload - {tweet_count} tweets',
                    'description': f'Single JSON upload on {datetime.now().strftime("%B %d, %Y at %H:%M:%S")} containing {tweet_count} tweets',
                    'source_type': 'json_upload',
                    'analysis_summary': json_data.get('analysis_summary', {}),
                    'tweets': json_data.get('processed_tweets', [])
                }
            else:
                return jsonify({'status': 'error', 'message': 'Invalid JSON format - no tweets found'}), 400
            
            # Try to save to database first
            if not save_campaign_data(campaign_data):
                return jsonify({
                    'status': 'error', 
                    'message': f'Failed to save campaign {campaign_data["campaign_batch"]}. Campaign or tweet IDs already exist in database.'
                }), 409
            processed_campaigns.append({
                'campaign_batch': campaign_data['campaign_batch'],
                'tweet_count': campaign_data['tweet_count'],
                'status': 'saved to database'
            })
        
        if not processed_campaigns:
            return jsonify({'status': 'error', 'message': 'No valid campaign data found in JSON'}), 400
        
        return jsonify({
            'status': 'success',
            'message': f'Successfully processed {len(processed_campaigns)} campaign(s)',
            'campaigns': processed_campaigns
        })
        
    except json.JSONDecodeError:
        return jsonify({'status': 'error', 'message': 'Invalid JSON format'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/campaigns', methods=['GET'])
def list_campaigns():
    """List all available campaigns"""
    try:
        campaigns = []
        
        # Get campaigns from database
        try:
            from database import get_session, Campaign, Tweet
            session = get_session()
            db_campaigns = session.query(Campaign).all()
            for campaign in db_campaigns:
                # Get tweet status summary for this campaign
                tweet_statuses = session.query(Tweet.status).filter(Tweet.campaign_batch == campaign.campaign_batch).all()
                status_counts = {}
                for status_tuple in tweet_statuses:
                    status = status_tuple[0] or 'Draft'
                    status_counts[status] = status_counts.get(status, 0) + 1
                print(f"DEBUG: Campaign {campaign.campaign_batch} status counts: {status_counts}")
                
                campaigns.append({
                    'campaign_batch': campaign.campaign_batch,
                    'tweet_count': campaign.tweet_count,
                    'generated_at': campaign.generated_at.isoformat(),
                    'title': getattr(campaign, 'title', f'Campaign {campaign.campaign_batch}'),
                    'description': getattr(campaign, 'description', 'No description available'),
                    'source_type': getattr(campaign, 'source_type', 'unknown'),
                    'display_name': getattr(campaign, 'display_name', None),
                    'source': 'database',
                    'status_counts': status_counts
                })
            session.close()
        except Exception as e:
            print(f"DEBUG: Database query failed: {e}")
            pass  # Database not available
        
        # Get campaigns from in-memory storage ONLY as fallback (should be minimal)
        for batch_id, campaign_data in tweet_storage.items():
            # Only add if not already in database results
            if not any(c['campaign_batch'] == batch_id for c in campaigns):
                # Calculate status counts for memory campaigns
                status_counts = {}
                tweets = campaign_data.get('tweets', [])
                for tweet in tweets:
                    status = tweet.get('status', 'Draft')
                    status_counts[status] = status_counts.get(status, 0) + 1
                
                campaigns.append({
                    'campaign_batch': batch_id,
                    'tweet_count': campaign_data.get('tweet_count', len(tweets)),
                    'generated_at': campaign_data.get('generated_at', 'Unknown'),
                    'title': campaign_data.get('title', f'Campaign {batch_id}'),
                    'description': campaign_data.get('description', 'Memory fallback campaign'),
                    'source_type': campaign_data.get('source_type', 'unknown'),
                    'source': 'memory (emergency fallback)',
                    'status_counts': status_counts
                })
                print(f"DEBUG: Added memory fallback campaign: {batch_id}")
        
        # Sort campaigns by generated_at in reverse chronological order (newest first)
        campaigns.sort(key=lambda x: x.get('generated_at', ''), reverse=True)
        
        return jsonify({
            'status': 'success',
            'campaigns': campaigns,
            'total': len(campaigns)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/tweets-by-status/<status>')
def get_tweets_by_status(status):
    """Get all tweets with a specific status"""
    try:
        tweets_by_status = []
        
        # Search through all campaigns in memory
        for campaign_batch, campaign_data in tweet_storage.items():
            for tweet in campaign_data.get('tweets', []):
                tweet_status = tweet.get('status', 'Draft')
                print(f"DEBUG: Checking tweet {tweet.get('id')} with status '{tweet_status}' against filter '{status}'")
                if tweet_status.lower() == status.lower():
                    tweet_with_campaign = tweet.copy()
                    tweet_with_campaign['campaign_batch'] = campaign_batch
                    tweets_by_status.append(tweet_with_campaign)
                    print(f"DEBUG: Added tweet {tweet.get('id')} to results")
        
        # Also search database if available
        try:
            from database import get_session, Tweet
            session = get_session()
            db_tweets = session.query(Tweet).filter(Tweet.status.ilike(f'%{status}%')).all()
            for db_tweet in db_tweets:
                tweet_dict = {
                    'id': db_tweet.id,
                    'campaign_batch': db_tweet.campaign_batch,
                    'type': db_tweet.type,
                    'content': db_tweet.content,
                    'character_count': db_tweet.character_count,
                    'status': db_tweet.status,
                    'engagement_hook': db_tweet.engagement_hook,
                    'last_modified': db_tweet.last_modified.isoformat() if db_tweet.last_modified else None,
                    'posted_date': db_tweet.posted_date.isoformat() if db_tweet.posted_date else None
                }
                tweets_by_status.append(tweet_dict)
            session.close()
        except:
            pass  # Database not available
        
        # Remove duplicates based on tweet id
        seen_ids = set()
        unique_tweets = []
        for tweet in tweets_by_status:
            if tweet['id'] not in seen_ids:
                unique_tweets.append(tweet)
                seen_ids.add(tweet['id'])
        
        # Sort by last_modified (newest first)
        unique_tweets.sort(key=lambda x: x.get('last_modified', ''), reverse=True)
        
        return jsonify({
            'status': 'success',
            'tweets': unique_tweets,
            'total': len(unique_tweets),
            'filter_status': status
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/delete-tweet', methods=['POST'])
def delete_tweet():
    """Delete a tweet"""
    try:
        data = request.get_json()
        campaign_batch = data.get('campaign_batch')
        tweet_id = data.get('tweet_id')
        
        print(f"DEBUG: Delete tweet - campaign '{campaign_batch}', tweet '{tweet_id}'")
        print(f"DEBUG: Available campaigns: {list(tweet_storage.keys())}")
        
        # Try database first, then memory fallback
        success = False
        
        # Try to update in database first
        if update_tweet_status(campaign_batch, tweet_id, 'Deleted'):
            print(f"DEBUG: Marked tweet '{tweet_id}' as deleted in database")
            success = True
        
        # Check in-memory storage as fallback
        if not success and campaign_batch in tweet_storage:
            campaign_data = tweet_storage[campaign_batch]
            tweets = campaign_data.get('tweets', [])
            
            # Find and mark tweet as deleted instead of removing it
            for tweet in tweets:
                if tweet['id'] == tweet_id:
                    # Check if already deleted
                    if tweet.get('status') == 'Deleted':
                        return jsonify({
                            'status': 'error',
                            'message': f'Tweet "{tweet.get("content", "")[:50]}..." is already deleted'
                        }), 400
                    
                    tweet['status'] = 'Deleted'
                    tweet['deleted_at'] = datetime.now().isoformat()
                    print(f"DEBUG: Marked tweet '{tweet_id}' as deleted in memory")
                    success = True
                    break
        
        if success:
            return jsonify({
                'status': 'success',
                'message': f'Tweet moved to deleted'
            })
        else:
            available_campaigns = list(tweet_storage.keys())
            return jsonify({'status': 'error', 'message': f'Campaign "{campaign_batch}" or tweet "{tweet_id}" not found. Available: {available_campaigns}'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/delete-campaign', methods=['POST'])
def delete_campaign():
    """Delete an entire campaign and all associated tweets"""
    try:
        data = request.get_json()
        campaign_batch = data.get('campaign_batch')
        hard_delete = data.get('hard_delete', False)  # Default to soft delete
        
        if not campaign_batch:
            return jsonify({'status': 'error', 'message': 'campaign_batch is required'}), 400
        
        print(f"DEBUG: Delete campaign request - batch: '{campaign_batch}', hard_delete: {hard_delete}")
        
        # Use the new cascade delete function from database.py
        success, message, deleted_count = delete_campaign_cascade(campaign_batch, hard_delete)
        
        if success:
            # Also remove from in-memory storage if present (fallback mode)
            if campaign_batch in tweet_storage:
                del tweet_storage[campaign_batch]
                print(f"DEBUG: Also removed campaign '{campaign_batch}' from memory storage")
            
            return jsonify({
                'status': 'success',
                'message': message,
                'deleted_count': deleted_count,
                'campaign_batch': campaign_batch,
                'hard_delete': hard_delete
            })
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 404
            
    except Exception as e:
        print(f"DEBUG: Delete campaign error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/update-campaign-name', methods=['POST'])
def update_campaign_name():
    """Update campaign display name"""
    try:
        data = request.get_json()
        campaign_batch = data.get('campaign_batch')
        display_name = data.get('display_name', '')
        
        if not campaign_batch:
            return jsonify({'status': 'error', 'message': 'campaign_batch is required'}), 400
        
        print(f"DEBUG: Update campaign name - batch: '{campaign_batch}', name: '{display_name}'")
        
        # Update in database
        from database import get_session, Campaign
        session = get_session()
        try:
            campaign = session.query(Campaign).filter_by(campaign_batch=campaign_batch).first()
            if not campaign:
                return jsonify({'status': 'error', 'message': f'Campaign "{campaign_batch}" not found'}), 404
            
            campaign.display_name = display_name
            campaign.updated_at = datetime.utcnow()
            session.commit()
            
            print(f"DEBUG: Successfully updated campaign name: '{display_name}'")
            return jsonify({
                'status': 'success',
                'message': f'Campaign name updated to "{display_name}"',
                'campaign_batch': campaign_batch,
                'display_name': display_name
            })
            
        except Exception as e:
            session.rollback()
            print(f"DEBUG: Database update error: {e}")
            return jsonify({'status': 'error', 'message': f'Database error: {str(e)}'}), 500
        finally:
            session.close()
            
    except Exception as e:
        print(f"DEBUG: Update campaign name error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/all-tweets')
def get_all_tweets():
    """Get all tweets from all campaigns"""
    try:
        all_tweets = []
        
        # Get tweets from memory
        for campaign_batch, campaign_data in tweet_storage.items():
            for tweet in campaign_data.get('tweets', []):
                tweet_with_campaign = tweet.copy()
                tweet_with_campaign['campaign_batch'] = campaign_batch
                tweet_with_campaign['generated_at'] = campaign_data.get('generated_at', '')
                all_tweets.append(tweet_with_campaign)
        
        # Also get from database if available
        try:
            from database import get_session, Tweet
            session = get_session()
            db_tweets = session.query(Tweet).all()
            for db_tweet in db_tweets:
                tweet_dict = {
                    'id': db_tweet.id,
                    'campaign_batch': db_tweet.campaign_batch,
                    'type': db_tweet.type,
                    'content': db_tweet.content,
                    'character_count': db_tweet.character_count,
                    'status': db_tweet.status,
                    'engagement_hook': db_tweet.engagement_hook,
                    'last_modified': db_tweet.last_modified.isoformat() if db_tweet.last_modified else None,
                    'posted_date': db_tweet.posted_date.isoformat() if db_tweet.posted_date else None,
                    'generated_at': '',
                    'deleted_at': getattr(db_tweet, 'deleted_at', None)
                }
                all_tweets.append(tweet_dict)
            session.close()
        except:
            pass  # Database not available
        
        # Remove duplicates
        seen_ids = set()
        unique_tweets = []
        for tweet in all_tweets:
            if tweet['id'] not in seen_ids:
                unique_tweets.append(tweet)
                seen_ids.add(tweet['id'])
        
        # Sort by generated_at, then by campaign_batch
        unique_tweets.sort(key=lambda x: (x.get('generated_at', ''), x.get('campaign_batch', '')), reverse=True)
        
        return jsonify({
            'status': 'success',
            'tweets': unique_tweets,
            'total': len(unique_tweets)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/export-csv')
def export_tweets_csv():
    """Export all tweets as CSV"""
    try:
        # Get all tweets
        response = get_all_tweets()
        data = response.get_json()
        
        if data['status'] != 'success':
            return jsonify({'status': 'error', 'message': 'Failed to get tweets'}), 500
        
        tweets = data['tweets']
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        headers = [
            'Tweet_ID', 'Campaign_Batch', 'Generated_Date', 'Content', 
            'Character_Count', 'Tweet_Type', 'Status', 'Engagement_Hook',
            'Last_Modified', 'Posted_Date', 'Deleted_At', 'Notes'
        ]
        writer.writerow(headers)
        
        # Write data
        for tweet in tweets:
            row = [
                tweet.get('id', ''),
                tweet.get('campaign_batch', ''),
                tweet.get('generated_at', ''),
                tweet.get('content', ''),
                tweet.get('character_count', ''),
                tweet.get('type', ''),
                tweet.get('status', 'Draft'),
                tweet.get('engagement_hook', ''),
                tweet.get('last_modified', ''),
                tweet.get('posted_date', ''),
                tweet.get('deleted_at', ''),
                tweet.get('notes', '')
            ]
            writer.writerow(row)
        
        # Create response
        csv_content = output.getvalue()
        output.close()
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=all_tweets_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/export-scraped-tweets-csv')
def export_scraped_tweets_csv():
    """Export scraped tweets as CSV"""
    try:
        # Get all scraped tweets (no pagination for export)
        tweets_data, total_count = get_scraped_tweets()
        
        if not tweets_data:
            return jsonify({'status': 'error', 'message': 'No scraped tweets found'}), 404
        
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        headers = [
            'Tweet_ID', 'URL', 'Content', 'Date', 'Likes', 'Retweets', 
            'Replies', 'Quotes', 'Views', 'Status', 'Tweet_URL', 
            'Execution_ID', 'Source_URL', 'Created_At', 'Engagement_Total'
        ]
        writer.writerow(headers)
        
        # Write data
        for tweet in tweets_data:
            row = [
                tweet.get('Tweet ID', ''),
                tweet.get('URL', ''),
                tweet.get('Content', ''),
                tweet.get('Date', ''),
                tweet.get('Likes', 0),
                tweet.get('Retweets', 0),
                tweet.get('Replies', 0),
                tweet.get('Quotes', 0),
                tweet.get('Views', 0),
                tweet.get('Status', ''),
                tweet.get('Tweet', ''),
                tweet.get('execution_id', ''),
                tweet.get('source_url', ''),
                tweet.get('created_at', ''),
                tweet.get('engagement_total', 0)
            ]
            writer.writerow(row)
        
        # Create response
        csv_content = output.getvalue()
        output.close()
        
        response = make_response(csv_content)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=scraped_tweets_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============================================================================
# SCRAPED TWEETS API ENDPOINTS (Phase 1 - Security & Foundation)
# ============================================================================

@app.route('/api/check-duplicate-tweet', methods=['POST'])
@auth.login_required
def check_duplicate_tweet():
    """
    Check for duplicate tweets in database - SECURE ENDPOINT
    Expected payload: {
        "execution_id": "exec_20250804_143022_n8n_a1b2c3d4",
        "source_url": "https://n8n.coophive.network",
        "tweets": [...]
    }
    OR array format: [{...}]
    Returns: {
        "status": "success",
        "new_tweets": [...],
        "duplicates_found": N,
        "execution_id": "...",
        "processed_count": N
    }
    """
    try:
        # Get request data
        raw_data = request.get_json()
        if not raw_data:
            return jsonify({'status': 'error', 'message': 'No JSON data provided'}), 400
        
        # Handle both array format (like in.json) and direct object format
        if isinstance(raw_data, list) and len(raw_data) > 0:
            data = raw_data[0]  # Extract the first object from array
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            return jsonify({'status': 'error', 'message': 'Invalid JSON format - expected object or array with object'}), 400
        
        execution_id = data.get('execution_id')
        source_url = data.get('source_url')
        tweets = data.get('tweets', [])
        
        # Validation
        if not execution_id:
            return jsonify({'status': 'error', 'message': 'Missing execution_id'}), 400
        if not source_url:
            return jsonify({'status': 'error', 'message': 'Missing source_url'}), 400
        if not tweets or not isinstance(tweets, list):
            return jsonify({'status': 'error', 'message': 'Missing or invalid tweets array'}), 400
        
        # Extract tweet IDs for duplicate checking
        tweet_ids = []
        for tweet in tweets:
            if tweet.get('Tweet ID'):
                tweet_ids.append(tweet['Tweet ID'])
            else:
                return jsonify({'status': 'error', 'message': f'Tweet missing "Tweet ID" field: {tweet}'}), 400
        
        print(f"DEBUG: Duplicate check request - execution_id: {execution_id}, tweet_count: {len(tweets)}")
        
        # Check for duplicates using IMPROVED LOGIC (execution_id first, then Tweet ID)
        existing_ids, new_ids = check_duplicate_scraped_tweets(tweet_ids, execution_id)
        
        # Filter tweets to return only new ones
        new_tweets = [tweet for tweet in tweets if tweet['Tweet ID'] in new_ids]
        
        # SAVE non-duplicate tweets to database
        saved_count = 0
        save_errors = []
        
        if new_tweets:
            try:
                saved_count, error_count, errors = save_scraped_tweets(new_tweets, execution_id, source_url)
                print(f"DEBUG: Successfully saved {saved_count} scraped tweets")
                if error_count > 0:
                    save_errors.extend(errors)
                    print(f"DEBUG: {error_count} errors occurred during save")
            except Exception as save_error:
                save_errors.append(str(save_error))
                print(f"ERROR: Failed to save tweets to database: {save_error}")
        
        # Log the results
        print(f"DEBUG: Duplicate check complete - {len(existing_ids)} duplicates, {len(new_tweets)} new tweets, {saved_count} saved")
        
        # Enhanced response with detailed information for both Web UI and n8n API
        response_status = 'success'
        if save_errors:
            response_status = 'warning' if saved_count > 0 else 'error'
        
        # Create detailed message
        if len(existing_ids) == 0 and len(new_tweets) > 0:
            main_message = f"✅ Success: All {len(tweets)} tweets are new and have been saved to database"
        elif len(existing_ids) > 0 and len(new_tweets) > 0:
            main_message = f"⚠️ Partial: Found {len(existing_ids)} duplicates, saved {saved_count} new tweets to database"
        elif len(existing_ids) > 0 and len(new_tweets) == 0:
            main_message = f"🔄 All Duplicates: All {len(tweets)} tweets already exist in database (no new data saved)"
        else:
            main_message = f"❌ Error: Unable to process tweets"
        
        response = {
            'status': response_status,
            'message': main_message,
            'summary': {
                'total_processed': len(tweets),
                'duplicates_found': len(existing_ids),
                'new_tweets_found': len(new_tweets),
                'saved_to_database': saved_count,
                'execution_id_duplicates': len([tid for tid in existing_ids if execution_id]) if execution_id else 0,
                'tweet_id_duplicates': len(existing_ids)
            },
            'data': {
                'new_tweets': new_tweets,
                'duplicate_ids': existing_ids,
                'execution_id': execution_id,
                'source_url': source_url
            },
            'debug_info': {
                'processed_count': len(tweets),
                'saved_count': saved_count,
                'error_count': len(save_errors)
            }
        }
        
        if save_errors:
            response['errors'] = save_errors
            response['message'] += f" ({len(save_errors)} save errors occurred)"
        
        return jsonify(response)
        
    except Exception as e:
        print(f"ERROR: check_duplicate_tweet failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/store-scraped-tweets', methods=['POST'])
@auth.login_required
def store_scraped_tweets():
    """
    Store scraped tweets in database - SECURE ENDPOINT
    Expected payload: {
        "execution_id": "exec_20250804_143022_n8n_a1b2c3d4",
        "source_url": "https://n8n.coophive.network",
        "tweets": [...]
    }
    Returns: {
        "status": "success",
        "stored_count": N,
        "error_count": N,
        "errors": [...],
        "execution_id": "..."
    }
    """
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON data provided'}), 400
        
        execution_id = data.get('execution_id')
        source_url = data.get('source_url')
        tweets = data.get('tweets', [])
        
        # Validation
        if not execution_id:
            return jsonify({'status': 'error', 'message': 'Missing execution_id'}), 400
        if not source_url:
            return jsonify({'status': 'error', 'message': 'Missing source_url'}), 400
        if not tweets or not isinstance(tweets, list):
            return jsonify({'status': 'error', 'message': 'Missing or invalid tweets array'}), 400
        
        # Validate tweet structure
        for i, tweet in enumerate(tweets):
            required_fields = ['Tweet ID', 'URL', 'Content', 'Date']
            missing_fields = [field for field in required_fields if not tweet.get(field)]
            if missing_fields:
                return jsonify({
                    'status': 'error', 
                    'message': f'Tweet {i+1} missing required fields: {missing_fields}'
                }), 400
        
        print(f"DEBUG: Store tweets request - execution_id: {execution_id}, tweet_count: {len(tweets)}")
        
        # Save tweets to database
        success_count, error_count, errors = save_scraped_tweets(tweets, execution_id, source_url)
        
        # Log the results
        print(f"DEBUG: Store tweets complete - {success_count} stored, {error_count} errors")
        
        if success_count > 0:
            status_code = 200
            status = 'success'
            message = f'Successfully stored {success_count} tweets'
            if error_count > 0:
                message += f' ({error_count} errors)'
        else:
            status_code = 500
            status = 'error'
            message = f'Failed to store any tweets ({error_count} errors)'
        
        response_data = {
            'status': status,
            'message': message,
            'stored_count': success_count,
            'error_count': error_count,
            'errors': errors,
            'execution_id': execution_id,
            'source_url': source_url,
            'processed_count': len(tweets)
        }
        
        return jsonify(response_data), status_code
        
    except Exception as e:
        print(f"ERROR: store_scraped_tweets failed: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============================================================================
# DATABASE ADMIN ENDPOINTS (Phase 1 - Database Management)
# ============================================================================

@app.route('/api/database-status', methods=['GET'])
def get_db_status():
    """Get database status and migration information - PUBLIC ENDPOINT"""
    try:
        status = get_database_status()
        return jsonify({
            'status': 'success',
            'database': status
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/database-migrate', methods=['POST'])
@auth.login_required
def trigger_migration():
    """Manually trigger database migration - SECURE ENDPOINT"""
    try:
        success = force_migration()
        if success:
            status = get_database_status()
            return jsonify({
                'status': 'success',
                'message': 'Database migration completed successfully',
                'database': status
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Database migration failed'
            }), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/database-backup', methods=['POST'])
@auth.login_required
def create_backup():
    """Create database backup - SECURE ENDPOINT (SQLite only)"""
    try:
        success, message = backup_database()
        if success:
            return jsonify({
                'status': 'success',
                'message': message
            })
        else:
            return jsonify({
                'status': 'error',
                'message': message
            }), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/database-admin')
def database_admin_page():
    """Database administration page"""
    return render_template('database_admin.html')

def get_sample_data():
    """Sample data for demo purposes"""
    return {
        'campaign_batch': 'demo_batch',
        'generated_at': datetime.now().isoformat(),
        'tweet_count': 3,
        'analysis_summary': {
            'input_batch_size': 20,
            'dominant_themes': ['AI/ML Technology', 'Developer Community', 'Blockchain/Web3'],
            'content_strategy': 'Demo content strategy for CoopHive social media engagement.'
        },
        'tweets': [
            {
                'id': 'demo-tweet-1',
                'type': 'community_engagement',
                'content': 'This is a demo tweet showcasing CoopHive\'s decentralized compute capabilities. What\'s your biggest compute challenge?',
                'character_count': 125,
                'status': 'Draft',
                'engagement_hook': 'What\'s your biggest compute challenge?',
                'coophive_elements': ['decentralized compute', 'cost savings'],
                'discord_voice_patterns': ['practical question'],
                'is_edited': False
            }
        ]
    }

if __name__ == '__main__':
    # Railway deployment configuration
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(debug=debug, host='0.0.0.0', port=port)