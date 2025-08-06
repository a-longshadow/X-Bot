from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Boolean, JSON, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import json

Base = declarative_base()

# Database version for migration tracking
CURRENT_DB_VERSION = 3

# Global engine and session factory for connection reuse
_engine = None
_Session = None

class DatabaseVersion(Base):
    __tablename__ = 'database_version'
    
    id = Column(Integer, primary_key=True)
    version = Column(Integer, default=CURRENT_DB_VERSION)
    updated_at = Column(DateTime, default=datetime.utcnow)
    migration_notes = Column(Text)

class Campaign(Base):
    __tablename__ = 'campaigns'
    
    campaign_batch = Column(String(100), primary_key=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    tweet_count = Column(Integer, default=0)
    analysis_summary = Column(JSON)
    title = Column(String(200))
    description = Column(Text)
    source_type = Column(String(50))
    display_name = Column(String(300))  # Human-readable campaign name
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Tweet(Base):
    __tablename__ = 'tweets'
    
    id = Column(String(100), primary_key=True)
    campaign_batch = Column(String(100))
    type = Column(String(50))
    content = Column(Text)
    character_count = Column(Integer)
    status = Column(String(20), default='Draft')
    engagement_hook = Column(Text)
    coophive_elements = Column(JSON)
    discord_voice_patterns = Column(JSON)
    theme_connection = Column(Text)
    is_edited = Column(Boolean, default=False)
    last_modified = Column(DateTime, default=datetime.utcnow)
    posted_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class ScrapedTweet(Base):
    __tablename__ = 'scraped_tweets'
    
    tweet_id = Column(String(50), primary_key=True)  # Maps to "Tweet ID"
    url = Column(Text)                                # Maps to "URL"
    content = Column(Text)                           # Maps to "Content"
    likes = Column(Integer, default=0)               # Maps to "Likes"
    retweets = Column(Integer, default=0)            # Maps to "Retweets"
    replies = Column(Integer, default=0)             # Maps to "Replies"  
    quotes = Column(Integer, default=0)              # Maps to "Quotes"
    views = Column(Integer, default=0)               # Maps to "Views"
    date = Column(DateTime)                          # Maps to "Date"
    status = Column(String(20), default='success')  # Maps to "Status"
    tweet_url = Column(Text)                         # Maps to "Tweet"
    execution_id = Column(String(100))               # N8N execution tracking
    source_url = Column(String(200))                 # N8N source URL
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def get_database_url():
    """Get database URL from environment or use SQLite for local development"""
    if os.environ.get('DATABASE_URL'):
        # Railway provides DATABASE_URL for PostgreSQL
        database_url = os.environ.get('DATABASE_URL')
        # Fix for SQLAlchemy 2.0 - replace postgres:// with postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    else:
        return 'sqlite:///tweets.db'

def get_database_version():
    """Get current database version"""
    global _engine
    if _engine is None:
        return 0
    
    # Check if database_version table exists
    inspector = inspect(_engine)
    if 'database_version' not in inspector.get_table_names():
        return 0
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    try:
        version_record = session.query(DatabaseVersion).first()
        if version_record:
            return version_record.version
        return 0
    except Exception:
        return 0
    finally:
        session.close()

def set_database_version(version, notes=""):
    """Set database version"""
    global _engine
    if _engine is None:
        return False
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    try:
        # Delete existing version records
        session.query(DatabaseVersion).delete()
        
        # Create new version record
        version_record = DatabaseVersion(
            version=version,
            updated_at=datetime.utcnow(),
            migration_notes=notes
        )
        session.add(version_record)
        session.commit()
        print(f"DEBUG: Database version set to {version}: {notes}")
        return True
    except Exception as e:
        session.rollback()
        print(f"DEBUG: Failed to set database version: {e}")
        return False
    finally:
        session.close()

def migrate_database():
    """Perform database migrations"""
    global _engine
    if _engine is None:
        return False
    
    current_version = get_database_version()
    print(f"DEBUG: Current database version: {current_version}, Target version: {CURRENT_DB_VERSION}")
    
    if current_version == CURRENT_DB_VERSION:
        print("DEBUG: Database is up to date")
        return True
    
    if current_version == 0:
        print("DEBUG: Fresh database - creating all tables")
        Base.metadata.create_all(_engine)
        set_database_version(CURRENT_DB_VERSION, "Initial database creation")
        return True
    
    # Perform incremental migrations
    Session = sessionmaker(bind=_engine)
    session = Session()
    
    try:
        if current_version < 2:
            print("DEBUG: Migrating to version 2 - Enhanced scraped tweets schema")
            
            # Check if scraped_tweets table exists, if not create it
            inspector = inspect(_engine)
            if 'scraped_tweets' not in inspector.get_table_names():
                print("DEBUG: Creating scraped_tweets table")
                ScrapedTweet.__table__.create(_engine)
            else:
                print("DEBUG: scraped_tweets table already exists")
            
            # Update version
            set_database_version(2, "Added scraped_tweets table with enhanced duplicate checking")
        
        # Migration to version 3 - Add display_name column to campaigns
        if current_version < 3:
            print("DEBUG: Migrating to version 3 - Adding display_name column to campaigns")
            
            # Add display_name column to campaigns table
            try:
                session.execute('ALTER TABLE campaigns ADD COLUMN display_name VARCHAR(300)')
                print("DEBUG: Added display_name column to campaigns table")
            except Exception as e:
                # Column might already exist, check if it's a duplicate column error
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("DEBUG: display_name column already exists, skipping")
                else:
                    raise e
            
            # Update version
            set_database_version(3, "Added display_name column to campaigns for human-readable names")
        
        session.commit()
        print(f"DEBUG: Database migration completed - now at version {CURRENT_DB_VERSION}")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"DEBUG: Database migration failed: {e}")
        return False
    finally:
        session.close()

def init_database():
    """Initialize database connection and perform migrations"""
    global _engine, _Session
    database_url = get_database_url()
    
    print(f"DEBUG: Initializing database with URL: {database_url}")
    
    # Create engine
    _engine = create_engine(database_url, echo=False, pool_recycle=3600)
    
    # Create minimal tables needed for version checking
    DatabaseVersion.__table__.create(_engine, checkfirst=True)
    
    # Perform migrations
    if migrate_database():
        _Session = sessionmaker(bind=_engine, autoflush=True)
        print(f"DEBUG: Database initialized successfully at version {CURRENT_DB_VERSION}")
        return _engine
    else:
        print("DEBUG: Database migration failed")
        return None

def get_session():
    """Get database session"""
    global _Session, _engine
    if _Session is None or _engine is None:
        init_database()
    # Create a new session but ensure it's bound to the same engine
    session = _Session()
    # Force autoflush and autocommit off for explicit control
    session.autoflush = True
    session.autocommit = False
    return session

def save_campaign_data(campaign_data):
    """Save campaign and tweets to database with smart collision handling and display names"""
    global _engine
    if _engine is None:
        init_database()
    
    original_batch = campaign_data['campaign_batch']
    print(f"DEBUG: Saving campaign {original_batch} with {len(campaign_data.get('tweets', []))} tweets")
    
    # Handle campaign batch ID collision
    unique_campaign_batch = get_unique_campaign_batch(original_batch)
    if unique_campaign_batch != original_batch:
        print(f"DEBUG: Campaign batch collision resolved: {original_batch} -> {unique_campaign_batch}")
        campaign_data['campaign_batch'] = unique_campaign_batch
    
    # Generate human-readable display name
    display_name = generate_display_name(campaign_data)
    print(f"DEBUG: Generated display name: '{display_name}'")
    
    # Create a fresh session for this operation
    Session = sessionmaker(bind=_engine)
    session = Session()
    
    try:
        # Handle tweet ID collisions
        tweets_to_save = campaign_data.get('tweets', [])
        for tweet_data in tweets_to_save:
            original_id = tweet_data['id']
            unique_id = get_unique_tweet_id(original_id, unique_campaign_batch)
            if unique_id != original_id:
                print(f"DEBUG: Tweet ID collision resolved: {original_id} -> {unique_id}")
                tweet_data['id'] = unique_id
            # Update campaign_batch reference in tweet
            tweet_data['campaign_batch'] = unique_campaign_batch
        
        # Save campaign with display name
        campaign = Campaign(
            campaign_batch=unique_campaign_batch,
            generated_at=datetime.fromisoformat(campaign_data['generated_at']),
            tweet_count=len(tweets_to_save),  # Use actual count
            analysis_summary=campaign_data.get('analysis_summary', {}),
            title=campaign_data.get('title', ''),
            description=campaign_data.get('description', ''),
            source_type=campaign_data.get('source_type', 'api'),
            display_name=display_name
        )
        session.add(campaign)
        
        # Save tweets
        for i, tweet_data in enumerate(tweets_to_save):
            print(f"DEBUG: Saving tweet {i+1}: {tweet_data.get('id', 'NO_ID')}")
            tweet = Tweet(
                id=tweet_data['id'],
                campaign_batch=unique_campaign_batch,
                type=tweet_data['type'],
                content=tweet_data['content'],
                character_count=tweet_data['character_count'],
                status=tweet_data.get('status', 'Draft'),
                engagement_hook=tweet_data.get('engagement_hook', ''),
                coophive_elements=tweet_data.get('coophive_elements', []),
                discord_voice_patterns=tweet_data.get('discord_voice_patterns', []),
                theme_connection=tweet_data.get('theme_connection', ''),
                is_edited=tweet_data.get('is_edited', False)
            )
            session.add(tweet)
        
        # Commit everything
        session.commit()
        print(f"DEBUG: Successfully saved campaign '{unique_campaign_batch}' with {len(tweets_to_save)} tweets")
        print(f"DEBUG: Display name: '{display_name}'")
        return True
        
    except Exception as e:
        session.rollback()
        print(f"DEBUG: Database save error: {e}")
        return False
    finally:
        session.close()

def get_campaign_data(campaign_batch):
    """Get campaign and tweets from database - SIMPLE VERSION"""
    global _engine
    if _engine is None:
        init_database()
    
    # Create a fresh session for this operation
    Session = sessionmaker(bind=_engine)
    session = Session()
    
    try:
        # Get campaign
        campaign = session.query(Campaign).filter_by(campaign_batch=campaign_batch).first()
        if not campaign:
            print(f"DEBUG: No campaign found in database for {campaign_batch}")
            return None
        
        # Get tweets
        tweets = session.query(Tweet).filter_by(campaign_batch=campaign_batch).all()
        print(f"DEBUG: Retrieved {len(tweets)} tweets from database for campaign {campaign_batch}")
        
        # Convert to dictionary format
        campaign_data = {
            'campaign_batch': campaign.campaign_batch,
            'generated_at': campaign.generated_at.isoformat(),
            'tweet_count': len(tweets),  # Use actual count from database
            'analysis_summary': campaign.analysis_summary or {},
            'title': campaign.title or '',
            'description': campaign.description or '',
            'source_type': campaign.source_type or 'unknown',
            'display_name': campaign.display_name or '',
            'tweets': []
        }
        
        for tweet in tweets:
            tweet_dict = {
                'id': tweet.id,
                'type': tweet.type,
                'content': tweet.content,
                'character_count': tweet.character_count,
                'status': tweet.status,
                'engagement_hook': tweet.engagement_hook,
                'coophive_elements': tweet.coophive_elements or [],
                'discord_voice_patterns': tweet.discord_voice_patterns or [],
                'theme_connection': tweet.theme_connection,
                'is_edited': tweet.is_edited,
                'last_modified': tweet.last_modified.isoformat() if tweet.last_modified else None,
                'posted_date': tweet.posted_date.isoformat() if tweet.posted_date else None
            }
            campaign_data['tweets'].append(tweet_dict)
        
        print(f"DEBUG: Returning campaign data with {len(campaign_data['tweets'])} tweets")
        return campaign_data
        
    except Exception as e:
        print(f"DEBUG: Database get error: {e}")
        return None
    finally:
        session.close()

def update_tweet_content(campaign_batch, tweet_id, new_content):
    """Update tweet content in database - SIMPLE VERSION"""
    global _engine
    if _engine is None:
        init_database()
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    try:
        tweet = session.query(Tweet).filter_by(
            campaign_batch=campaign_batch, 
            id=tweet_id
        ).first()
        
        if tweet:
            tweet.content = new_content
            tweet.character_count = len(new_content)
            tweet.is_edited = True
            tweet.last_modified = datetime.utcnow()
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        print(f"Database error: {e}")
        return False
    finally:
        session.close()

def update_tweet_status(campaign_batch, tweet_id, new_status):
    """Update tweet status in database - SIMPLE VERSION"""
    global _engine
    if _engine is None:
        init_database()
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    try:
        tweet = session.query(Tweet).filter_by(
            campaign_batch=campaign_batch, 
            id=tweet_id
        ).first()
        
        if tweet:
            tweet.status = new_status
            tweet.last_modified = datetime.utcnow()
            if new_status == 'Posted':
                tweet.posted_date = datetime.utcnow()
            session.commit()
            return True
        return False
    except Exception as e:
        session.rollback()
        print(f"Database error: {e}")
        return False
    finally:
        session.close()

# ============================================================================
# SCRAPED TWEETS MANAGEMENT FUNCTIONS
# ============================================================================

def check_duplicate_scraped_tweets(tweet_ids, execution_id=None):
    """
    Check which tweet IDs already exist in the scraped_tweets table
    IMPROVED LOGIC: Check execution_id first, then Tweet ID
    
    Args:
        tweet_ids: List of tweet IDs to check
        execution_id: Optional execution ID to check for duplicates within same execution
    
    Returns: (existing_ids, new_ids)
    """
    global _engine
    if _engine is None:
        init_database()
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    try:
        existing_ids = set()
        
        # Initialize tracking variables
        execution_duplicate_ids = set()
        tweet_duplicate_ids = set()
        
        # STEP 1: Check for duplicate execution_id (if provided)
        if execution_id:
            execution_duplicates = session.query(ScrapedTweet.tweet_id).filter(
                ScrapedTweet.execution_id == execution_id
            ).all()
            execution_duplicate_ids = {tweet.tweet_id for tweet in execution_duplicates}
            
            if execution_duplicate_ids:
                print(f"DEBUG: Found {len(execution_duplicate_ids)} tweets with same execution_id: {execution_id}")
                existing_ids.update(execution_duplicate_ids)
        
        # STEP 2: Check for duplicate Tweet IDs (global check)
        tweet_id_duplicates = session.query(ScrapedTweet.tweet_id).filter(
            ScrapedTweet.tweet_id.in_(tweet_ids)
        ).all()
        tweet_duplicate_ids = {tweet.tweet_id for tweet in tweet_id_duplicates}
        
        if tweet_duplicate_ids:
            print(f"DEBUG: Found {len(tweet_duplicate_ids)} tweets with duplicate Tweet IDs")
            existing_ids.update(tweet_duplicate_ids)
        
        # Calculate new tweet IDs
        new_ids = [tid for tid in tweet_ids if tid not in existing_ids]
        
        print(f"DEBUG: Checked {len(tweet_ids)} tweets - {len(existing_ids)} duplicates, {len(new_ids)} new")
        print(f"DEBUG: Execution duplicates: {len(execution_duplicate_ids)}, Tweet ID duplicates: {len(tweet_duplicate_ids)}")
        
        return list(existing_ids), new_ids
        
    except Exception as e:
        print(f"Database error checking duplicates: {e}")
        return [], tweet_ids  # Return all as new if error
    finally:
        session.close()

def save_scraped_tweets(tweets_data, execution_id, source_url):
    """
    Save scraped tweets to database
    tweets_data: List of tweet dictionaries from n8n
    Returns: (success_count, error_count, errors)
    """
    global _engine
    if _engine is None:
        init_database()
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    success_count = 0
    error_count = 0
    errors = []
    
    try:
        for tweet_data in tweets_data:
            try:
                # Parse the date string from Twitter API
                tweet_date = None
                if tweet_data.get('Date'):
                    try:
                        # Parse Twitter date format: "Mon Aug 04 17:15:25 +0000 2025"
                        tweet_date = datetime.strptime(tweet_data['Date'], "%a %b %d %H:%M:%S %z %Y")
                    except ValueError as e:
                        print(f"Date parse error for tweet {tweet_data.get('Tweet ID')}: {e}")
                        tweet_date = datetime.utcnow()
                
                # Create ScrapedTweet object
                scraped_tweet = ScrapedTweet(
                    tweet_id=tweet_data['Tweet ID'],
                    url=tweet_data.get('URL', ''),
                    content=tweet_data.get('Content', ''),
                    likes=int(tweet_data.get('Likes', 0)),
                    retweets=int(tweet_data.get('Retweets', 0)),
                    replies=int(tweet_data.get('Replies', 0)),
                    quotes=int(tweet_data.get('Quotes', 0)),
                    views=int(tweet_data.get('Views', 0)),
                    date=tweet_date,
                    status=tweet_data.get('Status', 'success'),
                    tweet_url=tweet_data.get('Tweet', ''),
                    execution_id=execution_id,
                    source_url=source_url
                )
                
                session.add(scraped_tweet)
                success_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = f"Error saving tweet {tweet_data.get('Tweet ID', 'unknown')}: {str(e)}"
                errors.append(error_msg)
                print(f"DEBUG: {error_msg}")
        
        # Commit all successfully created tweets
        if success_count > 0:
            session.commit()
            print(f"DEBUG: Successfully saved {success_count} scraped tweets")
        
        return success_count, error_count, errors
        
    except Exception as e:
        session.rollback()
        print(f"Database error saving scraped tweets: {e}")
        return 0, len(tweets_data), [f"Database error: {str(e)}"]
    finally:
        session.close()

def get_scraped_tweets(limit=None, offset=None, execution_id=None):
    """
    Retrieve scraped tweets from database with enhanced pagination support
    Returns: Tuple of (tweets_data, total_count)
    """
    global _engine
    if _engine is None:
        init_database()
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    try:
        # Base query
        query = session.query(ScrapedTweet)
        
        if execution_id:
            query = query.filter(ScrapedTweet.execution_id == execution_id)
        
        # Get total count before applying limit/offset
        total_count = query.count()
        
        # Order by date descending (newest first), then by created_at for consistency
        query = query.order_by(ScrapedTweet.date.desc(), ScrapedTweet.created_at.desc())
        
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        
        tweets = query.all()
        
        # Convert to dictionary format with enhanced data
        tweets_data = []
        for tweet in tweets:
            # Format the date for better display
            formatted_date = None
            if tweet.date:
                try:
                    formatted_date = tweet.date.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    formatted_date = str(tweet.date)
            
            tweets_data.append({
                'Tweet ID': tweet.tweet_id,
                'URL': tweet.url,
                'Content': tweet.content,
                'Likes': tweet.likes,
                'Retweets': tweet.retweets,
                'Replies': tweet.replies,
                'Quotes': tweet.quotes,
                'Views': tweet.views,
                'Date': formatted_date,
                'Status': tweet.status,
                'Tweet': tweet.tweet_url,
                'execution_id': tweet.execution_id,
                'source_url': tweet.source_url,
                'created_at': tweet.created_at.strftime("%Y-%m-%d %H:%M:%S") if tweet.created_at else None,
                'engagement_total': tweet.likes + tweet.retweets + tweet.replies + tweet.quotes
            })
        
        return tweets_data, total_count
        
    except Exception as e:
        print(f"Database error retrieving scraped tweets: {e}")
        return [], 0
    finally:
        session.close()

def get_scraped_tweets_stats():
    """Get statistics about scraped tweets"""
    global _engine
    if _engine is None:
        init_database()
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    try:
        from sqlalchemy import func
        
        # Basic counts
        total_tweets = session.query(ScrapedTweet).count()
        
        # Engagement stats
        engagement_stats = session.query(
            func.sum(ScrapedTweet.likes).label('total_likes'),
            func.sum(ScrapedTweet.retweets).label('total_retweets'),
            func.sum(ScrapedTweet.replies).label('total_replies'),
            func.sum(ScrapedTweet.views).label('total_views'),
            func.avg(ScrapedTweet.likes).label('avg_likes')
        ).first()
        
        # Date range
        date_range = session.query(
            func.min(ScrapedTweet.date).label('earliest'),
            func.max(ScrapedTweet.date).label('latest')
        ).first()
        
        # Execution stats
        execution_count = session.query(func.count(func.distinct(ScrapedTweet.execution_id))).scalar()
        
        return {
            'total_tweets': total_tweets,
            'total_likes': engagement_stats.total_likes or 0,
            'total_retweets': engagement_stats.total_retweets or 0,
            'total_replies': engagement_stats.total_replies or 0,
            'total_views': engagement_stats.total_views or 0,
            'avg_likes': round(engagement_stats.avg_likes or 0, 2),
            'earliest_date': date_range.earliest,
            'latest_date': date_range.latest,
            'execution_count': execution_count
        }
        
    except Exception as e:
        print(f"Database error getting scraped tweet stats: {e}")
        return {
            'total_tweets': 0,
            'total_likes': 0,
            'total_retweets': 0,
            'total_replies': 0,
            'total_views': 0,
            'avg_likes': 0,
            'earliest_date': None,
            'latest_date': None,
            'execution_count': 0
        }
    finally:
        session.close()

# ============================================================================
# DATABASE MANAGEMENT UTILITIES
# ============================================================================

def get_database_status():
    """Get comprehensive database status information"""
    global _engine
    if _engine is None:
        return {
            'status': 'disconnected',
            'version': 0,
            'target_version': CURRENT_DB_VERSION,
            'tables': [],
            'message': 'Database not initialized'
        }
    
    try:
        inspector = inspect(_engine)
        tables = inspector.get_table_names()
        current_version = get_database_version()
        
        return {
            'status': 'connected',
            'version': current_version,
            'target_version': CURRENT_DB_VERSION,
            'needs_migration': current_version != CURRENT_DB_VERSION,
            'tables': tables,
            'database_url': get_database_url(),
            'message': f'Database version {current_version} of {CURRENT_DB_VERSION}'
        }
    except Exception as e:
        return {
            'status': 'error',
            'version': 0,
            'target_version': CURRENT_DB_VERSION,
            'tables': [],
            'message': f'Database error: {str(e)}'
        }

def force_migration():
    """Force database migration - use with caution"""
    global _engine
    if _engine is None:
        print("DEBUG: Cannot migrate - database not initialized")
        return False
    
    print("DEBUG: Forcing database migration...")
    return migrate_database()

def backup_database(backup_path=None):
    """Create a backup of SQLite database (SQLite only)"""
    database_url = get_database_url()
    
    if not database_url.startswith('sqlite:///'):
        return False, "Backup only supported for SQLite databases"
    
    import shutil
    from datetime import datetime
    
    try:
        db_file = database_url.replace('sqlite:///', '')
        if not os.path.exists(db_file):
            return False, "Database file does not exist"
        
        if backup_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"tweets_backup_{timestamp}.db"
        
        shutil.copy2(db_file, backup_path)
        return True, f"Database backed up to {backup_path}"
        
    except Exception as e:
        return False, f"Backup failed: {str(e)}"

# ============================================================================
# ENHANCED CAMPAIGN MANAGEMENT FUNCTIONS
# ============================================================================

def generate_display_name(campaign_data):
    """Generate human-readable display name from campaign analysis summary"""
    try:
        analysis = campaign_data.get('analysis_summary', {})
        dominant_themes = analysis.get('dominant_themes', [])
        tweet_count = len(campaign_data.get('tweets', []))
        
        # Extract date from campaign_batch or generated_at
        date_str = ""
        if 'generated_at' in campaign_data:
            try:
                date_obj = datetime.fromisoformat(campaign_data['generated_at'].replace('Z', '+00:00'))
                date_str = date_obj.strftime("%b %d")
            except:
                pass
        
        # If no themes available, create generic name
        if not dominant_themes:
            if date_str:
                return f"Content Batch - {date_str} ({tweet_count} tweets)"
            else:
                return f"Content Batch ({tweet_count} tweets)"
        
        # Create name from first 1-2 themes
        if len(dominant_themes) >= 2:
            theme_part = f"{dominant_themes[0]} & {dominant_themes[1]}"
        else:
            theme_part = dominant_themes[0]
        
        # Clean up theme names (remove common prefixes/suffixes)
        theme_part = theme_part.replace("AI/ML ", "AI ").replace(" Technology", "").replace(" Community", "")
        
        if date_str:
            return f"{theme_part} - {date_str} ({tweet_count} tweets)"
        else:
            return f"{theme_part} ({tweet_count} tweets)"
            
    except Exception as e:
        print(f"DEBUG: Error generating display name: {e}")
        tweet_count = len(campaign_data.get('tweets', []))
        return f"Campaign ({tweet_count} tweets)"

def get_unique_campaign_batch(original_batch):
    """Get unique campaign batch ID by adding increment suffix if needed"""
    global _engine
    if _engine is None:
        return original_batch
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    
    try:
        # Check if original exists
        existing = session.query(Campaign).filter_by(campaign_batch=original_batch).first()
        if not existing:
            return original_batch
        
        # Find next available suffix
        counter = 2
        while counter <= 99:  # Reasonable limit
            candidate = f"{original_batch}-v{counter}"
            existing = session.query(Campaign).filter_by(campaign_batch=candidate).first()
            if not existing:
                return candidate
            counter += 1
        
        # If all suffixes exhausted, add timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%H%M%S")
        return f"{original_batch}-{timestamp}"
        
    except Exception as e:
        print(f"DEBUG: Error getting unique campaign batch: {e}")
        return original_batch
    finally:
        session.close()

def get_unique_tweet_id(original_id, campaign_batch):
    """Get unique tweet ID by adding increment suffix if needed"""
    global _engine
    if _engine is None:
        return original_id
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    
    try:
        # Check if original exists
        existing = session.query(Tweet).filter_by(id=original_id).first()
        if not existing:
            return original_id
        
        # Find next available suffix
        counter = 2
        while counter <= 99:  # Reasonable limit
            candidate = f"{original_id}-v{counter}"
            existing = session.query(Tweet).filter_by(id=candidate).first()
            if not existing:
                return candidate
            counter += 1
        
        # If all suffixes exhausted, add campaign suffix
        base_id = original_id.split('-')[-1] if '-' in original_id else original_id
        return f"{campaign_batch}-{base_id}"
        
    except Exception as e:
        print(f"DEBUG: Error getting unique tweet ID: {e}")
        return original_id
    finally:
        session.close()

def delete_campaign_cascade(campaign_batch, hard_delete=False):
    """Delete campaign and all associated tweets with cascade
    
    Args:
        campaign_batch: Campaign batch ID to delete
        hard_delete: If True, permanently delete from database. If False, mark as deleted.
    
    Returns:
        (success: bool, message: str, deleted_count: int)
    """
    global _engine
    if _engine is None:
        return False, "Database not initialized", 0
    
    Session = sessionmaker(bind=_engine)
    session = Session()
    
    try:
        # Check if campaign exists
        campaign = session.query(Campaign).filter_by(campaign_batch=campaign_batch).first()
        if not campaign:
            return False, f"Campaign '{campaign_batch}' not found", 0
        
        # Get associated tweets
        tweets = session.query(Tweet).filter_by(campaign_batch=campaign_batch).all()
        tweet_count = len(tweets)
        
        if hard_delete:
            # Permanently delete tweets first (foreign key constraint)
            for tweet in tweets:
                session.delete(tweet)
            
            # Delete campaign
            session.delete(campaign)
            
            session.commit()
            return True, f"Permanently deleted campaign '{campaign_batch}' and {tweet_count} tweets", tweet_count
        
        else:
            # Soft delete - mark as deleted
            for tweet in tweets:
                tweet.status = 'Deleted'
                tweet.last_modified = datetime.utcnow()
            
            # Mark campaign with special status (we could add a status column later)
            campaign.description = f"[DELETED] {campaign.description or ''}"
            campaign.updated_at = datetime.utcnow()
            
            session.commit()
            return True, f"Soft deleted campaign '{campaign_batch}' and {tweet_count} tweets", tweet_count
        
    except Exception as e:
        session.rollback()
        print(f"DEBUG: Error deleting campaign: {e}")
        return False, f"Delete failed: {str(e)}", 0
    finally:
        session.close() 