# CoopHive Content Manager

A sleek, modern Flask web application for reviewing and publishing AI-generated social media content.

## Features

🎨 **Modern UI**: Clean, animated interface with gradient backgrounds and smooth transitions  
🔍 **Tweet Review**: Edit tweets with real-time character counting and validation  
✅ **Approval Workflow**: Approve, reject, or modify tweets before publishing  
🚀 **X.com Integration**: Direct publishing to X.com via n8n webhook  
📊 **Campaign Analytics**: Track performance and engagement metrics  
🔐 **Secure Access**: Token-based authentication from email links  

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python app.py
```

### 3. Access the App
- **Home**: http://localhost:5000
- **Review**: http://localhost:5000/review/{campaign_batch}?token={secure_token}

## API Endpoints

### Receive Tweet Data (from n8n)
```
POST /api/receive-tweets
Content-Type: application/json

{
  "campaign_batch": "batch_2025-07-31_17-06",
  "secure_token": "...",
  "tweets": [...],
  "analysis_summary": {...}
}
```

### Save Tweet Edits
```
POST /api/save-tweet
Content-Type: application/json

{
  "campaign_batch": "batch_2025-07-31_17-06",
  "tweet_id": "2025-07-31-coophive-community-591035A",
  "content": "Updated tweet content..."
}
```

### Update Tweet Status
```
POST /api/update-status
Content-Type: application/json

{
  "campaign_batch": "batch_2025-07-31_17-06",
  "tweet_id": "2025-07-31-coophive-community-591035A",
  "status": "Approved"
}
```

### Post to X.com
```
POST /api/post-to-x
Content-Type: application/json

{
  "campaign_batch": "batch_2025-07-31_17-06",
  "tweet_id": "2025-07-31-coophive-community-591035A"
}
```

## n8n Integration

### Step 1: Update "POST to WebApp" Node
```
URL: http://your-flask-app.com/api/receive-tweets
Method: POST
Body: {{ $json }} (the web app payload from Generated Tweets Processor)
```

### Step 2: Create n8n Webhook for X.com Posting
```
Webhook URL: https://n8n.coophive.com/webhook/post-to-x
Trigger: POST request from Flask app
Action: Post tweet to X.com API
```

## Security

- **Token Validation**: Each campaign requires a secure token
- **24-Hour Expiry**: Tokens expire after 24 hours
- **Campaign Isolation**: Each campaign is isolated by batch ID
- **Input Sanitization**: All user inputs are validated

## Customization

### Styling
- Modify CSS in `templates/base.html`
- Update color scheme by changing gradient values
- Add new animations in the CSS animations section

### Features
- Add new API endpoints in `app.py`
- Extend tweet metadata in the templates
- Add new status types or workflow states

## Production Deployment

### Environment Variables
```bash
export FLASK_ENV=production
export SECRET_KEY=your-secret-key
export N8N_WEBHOOK_URL=https://n8n.coophive.com/webhook/post-to-x
```

### Database Integration
Replace in-memory `tweet_storage` with:
- PostgreSQL for production
- Redis for caching
- MongoDB for document storage

### Security Enhancements
- Add JWT token validation
- Implement rate limiting
- Add HTTPS/SSL certificates
- Set up CORS policies

## Architecture

```
Email Link → Flask App → Tweet Editor → n8n Webhook → X.com API
     ↓           ↓            ↓            ↓
   Token    Web Interface  Save Changes  Post Tweet
```

## Dependencies

- **Flask 3.0.0**: Web framework
- **requests 2.31.0**: HTTP client for webhook calls

**Total**: Only 2 dependencies for maximum simplicity and security.