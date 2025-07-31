from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import json

Base = declarative_base()

# Global engine and session factory for connection reuse
_engine = None
_Session = None

class Campaign(Base):
    __tablename__ = 'campaigns'
    
    campaign_batch = Column(String(100), primary_key=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
    tweet_count = Column(Integer, default=0)
    analysis_summary = Column(JSON)
    title = Column(String(200))
    description = Column(Text)
    source_type = Column(String(50))
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

def init_database():
    """Initialize database connection and create tables"""
    global _engine, _Session
    database_url = get_database_url()
    
    # For SQLite only, remove the old database file to ensure clean schema
    # Don't do this for PostgreSQL in production
    if database_url.startswith('sqlite:///'):
        db_file = database_url.replace('sqlite:///', '')
        if os.path.exists(db_file):
            print(f"DEBUG: Removing old database file: {db_file}")
            os.remove(db_file)
    
    _engine = create_engine(database_url, echo=False, pool_recycle=3600)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, autoflush=True)
    print(f"DEBUG: Database initialized with URL: {database_url}")
    return _engine

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
    """Save campaign and tweets to database - SIMPLE VERSION"""
    global _engine
    if _engine is None:
        init_database()
    
    print(f"DEBUG: Saving campaign {campaign_data['campaign_batch']} with {len(campaign_data.get('tweets', []))} tweets")
    
    # Create a fresh session for this operation
    Session = sessionmaker(bind=_engine)
    session = Session()
    
    try:
        # Check for existing campaign
        existing_campaign = session.query(Campaign).filter_by(campaign_batch=campaign_data['campaign_batch']).first()
        if existing_campaign:
            print(f"ERROR: Campaign {campaign_data['campaign_batch']} already exists in database")
            return False
        
        # Check for existing tweet IDs
        tweets_to_save = campaign_data.get('tweets', [])
        for tweet_data in tweets_to_save:
            existing_tweet = session.query(Tweet).filter_by(id=tweet_data['id']).first()
            if existing_tweet:
                print(f"ERROR: Tweet ID {tweet_data['id']} already exists in database")
                return False
        
        # Save campaign
        campaign = Campaign(
            campaign_batch=campaign_data['campaign_batch'],
            generated_at=datetime.fromisoformat(campaign_data['generated_at']),
            tweet_count=campaign_data['tweet_count'],
            analysis_summary=campaign_data.get('analysis_summary', {}),
            title=campaign_data.get('title', ''),
            description=campaign_data.get('description', ''),
            source_type=campaign_data.get('source_type', 'unknown')
        )
        session.add(campaign)
        
        # Save tweets
        tweets_to_save = campaign_data.get('tweets', [])
        for i, tweet_data in enumerate(tweets_to_save):
            print(f"DEBUG: Saving tweet {i+1}: {tweet_data.get('id', 'NO_ID')}")
            tweet = Tweet(
                id=tweet_data['id'],
                campaign_batch=campaign_data['campaign_batch'],
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
        print(f"DEBUG: Successfully saved {len(tweets_to_save)} tweets to database")
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