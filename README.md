# Gemini Chat Web App

A React + FastAPI chat application that provides a web interface for Google Gemini AI. Features real-time streaming responses via Server-Sent Events (SSE).

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Firebase Hosting                    │
│  ┌─────────────────────────────────────────┐    │
│  │      React Frontend (Vite + TS)         │    │
│  └─────────────────────────────────────────┘    │
│                    │                             │
│                    │ /api/* (proxy/rewrite)      │
│                    ▼                             │
│  ┌─────────────────────────────────────────┐    │
│  │   Cloud Run (FastAPI + Gemini API)      │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

## Features

- 💬 Real-time chat interface with streaming responses
- 🚀 FastAPI backend with async Gemini API integration
- 📝 Configurable system prompt
- 🔄 Conversation history maintained per session
- 🎨 Dark theme UI

## Prerequisites

- Node.js 18+
- Python 3.11+
- Google Cloud account (for deployment)
- Firebase CLI (`npm install -g firebase-tools`)
- Google Cloud CLI (`gcloud`)

## Local Development

### 1. Clone and Setup

```bash
cd cutlist-web-test

# Setup backend
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

### 2. Get Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create a new API key
3. Add it to `backend/.env`:
   ```
   GEMINI_API_KEY=your-api-key-here
   ```

### 3. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 4. Run Development Servers

**Option A: Using dev script (recommended)**
```bash
chmod +x dev.sh
./dev.sh
```

**Option B: Run separately**

Terminal 1 (Backend):
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8080
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

### 5. Open the App

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8080/docs

## Configuration

### System Prompt

Edit `backend/config/system_prompt.txt` to customize the AI's behavior and personality.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | Required |
| `GEMINI_MODEL` | Gemini model to use | `gemini-2.5-flash` |
| `HOST` | Backend host | `0.0.0.0` |
| `PORT` | Backend port | `8080` |

## Deployment

### 1. Setup Firebase Project

```bash
firebase login
firebase projects:create your-project-id
firebase use your-project-id
```

Update `.firebaserc` with your project ID.

### 2. Deploy Backend to Cloud Run

```bash
cd backend

# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# Set your Gemini API key as a secret (recommended)
gcloud secrets create gemini-api-key --data-file=- <<< "your-api-key"

# Deploy
gcloud run deploy gemini-chat-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest
```

### 3. Deploy Frontend to Firebase Hosting

```bash
# Build frontend
cd frontend
npm run build

# Deploy
cd ..
firebase deploy --only hosting
```

### 4. One-Command Deploy

After initial setup:
```bash
npm run deploy
```

## Project Structure

```
cutlist-web-test/
├── frontend/                    # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWindow.tsx   # Main chat UI
│   │   │   └── ChatWindow.css
│   │   ├── hooks/
│   │   │   └── useChat.ts       # Chat state management
│   │   ├── services/
│   │   │   └── api.ts           # Backend API client
│   │   ├── App.tsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.ts           # Vite config with API proxy
│
├── backend/                     # FastAPI backend
│   ├── app/
│   │   ├── main.py              # FastAPI app & routes
│   │   ├── config.py            # Configuration management
│   │   └── services/
│   │       └── gemini_service.py # Gemini API integration
│   ├── config/
│   │   └── system_prompt.txt    # AI system prompt
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── firebase.json                # Firebase Hosting config
├── .firebaserc                  # Firebase project config
├── dev.sh                       # Local dev script
├── package.json                 # Root package.json with scripts
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/chat/stream` | Stream chat response (SSE) |

### Chat Request Body

```json
{
  "message": "Hello, how are you?",
  "history": [
    {"role": "user", "content": "Previous message"},
    {"role": "model", "content": "Previous response"}
  ]
}
```

## Troubleshooting

### CORS Errors
The backend is configured to allow requests from `localhost:5173` and `localhost:3000`. For production, update the CORS settings in `backend/app/main.py`.

### Streaming Not Working
1. Check browser console for errors
2. Verify the Vite proxy is configured correctly
3. Test the backend directly: `curl -X POST http://localhost:8080/api/chat/stream -H "Content-Type: application/json" -d '{"message": "hi"}'`

### API Key Issues
1. Verify your API key at [Google AI Studio](https://aistudio.google.com)
2. Check `backend/.env` file exists and has the correct key
3. Restart the backend server after changing `.env`

## License

MIT
