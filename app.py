# CoopHive Tweet Review Flask App
# Simple, professional web app for reviewing and editing AI-generated tweets

from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
import os
from datetime import datetime
import secrets
import requests

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# In-memory storage for demo (replace with database in production)
tweet_storage = {}

@app.route('/')
def index():
    """Home page - redirect to review if campaign exists"""
    return render_template('index.html')

@app.route('/review/<campaign_batch>')
def review_tweets(campaign_batch):
    """Main tweet review interface"""
    token = request.args.get('token')
    
    # Basic token validation (enhance for production)
    if not token or not token.startswith(campaign_batch):
        return render_template('error.html', 
                             error="Invalid or expired access token"), 403
    
    # Get tweet data from storage or return sample data
    campaign_data = tweet_storage.get(campaign_batch, get_sample_data())
    
    return render_template('review.html', 
                         campaign=campaign_data,
                         campaign_batch=campaign_batch,
                         token=token)

@app.route('/api/receive-tweets', methods=['POST'])
def receive_tweets():
    """Endpoint to receive tweet data from n8n workflow"""
    try:
        data = request.get_json()
        campaign_batch = data.get('campaign_batch')
        
        if campaign_batch:
            tweet_storage[campaign_batch] = data
            return jsonify({
                'status': 'success',
                'message': f'Received {len(data.get("tweets", []))} tweets',
                'campaign_batch': campaign_batch
            })
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
        
        # Update tweet in storage
        if campaign_batch in tweet_storage:
            campaign_data = tweet_storage[campaign_batch]
            for tweet in campaign_data.get('tweets', []):
                if tweet['id'] == tweet_id:
                    tweet['content'] = new_content
                    tweet['character_count'] = len(new_content)
                    tweet['is_edited'] = True
                    tweet['last_modified'] = datetime.now().isoformat()
                    break
            
            return jsonify({
                'status': 'success',
                'message': 'Tweet saved successfully',
                'character_count': len(new_content)
            })
        else:
            return jsonify({'status': 'error', 'message': 'Campaign not found'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/post-to-x', methods=['POST'])
def post_to_x():
    """Trigger n8n webhook to post tweet to X.com"""
    try:
        data = request.get_json()
        tweet_id = data.get('tweet_id')
        campaign_batch = data.get('campaign_batch')
        
        # Get tweet content
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
        
        if campaign_batch in tweet_storage:
            campaign_data = tweet_storage[campaign_batch]
            for tweet in campaign_data.get('tweets', []):
                if tweet['id'] == tweet_id:
                    tweet['status'] = new_status
                    tweet['last_modified'] = datetime.now().isoformat()
                    break
            
            return jsonify({
                'status': 'success',
                'message': f'Tweet status updated to {new_status}'
            })
        else:
            return jsonify({'status': 'error', 'message': 'Campaign not found'}), 404
            
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

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