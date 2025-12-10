# Cutlist Web Application

Cutlist Web is a modern application designed to streamline woodworking and design projects by leveraging the power of Google Gemini AI. This app provides a real-time chat interface where users can interact with an AI assistant to generate, refine, and manage project designs. With its intuitive React-based frontend and a robust FastAPI backend, Cutlist Web ensures a seamless user experience for hobbyists and professionals alike.

Whether you're brainstorming ideas, creating detailed cut lists, or exploring 3D visualizations, Cutlist Web empowers you with AI-driven insights and tools to bring your projects to life. The app is built with scalability and customization in mind, making it suitable for both personal and collaborative use.

## Features

- 🌟 Real-time chat interface with streaming responses
- 🚀 FastAPI backend with Google Gemini API integration
- 🛠️ Configurable AI system prompt
- 🔄 Session-based conversation history
- 🎨 Dark theme UI for better user experience

## Prerequisites

Ensure the following tools are installed:

- Node.js 18+
- Python 3.11+
- Google Cloud CLI (`gcloud`)
- Firebase CLI (`npm install -g firebase-tools`)
- `uv` Python package (required for running backend scripts)

## Local Development

### 1. Clone the Repository

```bash
git clone https://github.com/RyanS161/cutlist-web.git
cd cutlist-web
```

### 2. Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# Add your GEMINI_API_KEY to the .env file
```

### 3. Frontend Setup

```bash
cd ../frontend
npm install
```

### 4. Run Development Servers

**Option A: Using the provided script**

```bash
chmod +x dev.sh
./dev.sh
```

**Option B: Run manually**

- **Backend**:
  ```bash
  cd backend
  source venv/bin/activate
  uvicorn app.main:app --reload --port 8080
  ```
- **Frontend**:
  ```bash
  cd frontend
  npm run dev
  ```

### 5. Access the Application

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API Docs: [http://localhost:8080/docs](http://localhost:8080/docs)

## Deployment

### 1. Firebase Hosting Setup

```bash
firebase login
firebase projects:create your-project-id
firebase use your-project-id
```

Update `.firebaserc` with your project ID.

### 2. Deploy Backend to Google Cloud Run

```bash
cd backend

# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

# Set your Gemini API key as a secret
gcloud secrets create gemini-api-key --data-file=- <<< "your-api-key"

# Deploy the backend
gcloud run deploy gemini-chat-api \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest
```

### 3. Deploy Frontend to Firebase Hosting

```bash
cd frontend
npm run build
cd ..
firebase deploy --only hosting
```

### 4. One-Command Deployment

After initial setup:

```bash
npm run deploy
```

## Project Structure

```
cutlist-web/
├── frontend/                    # React frontend
│   ├── src/
│   │   ├── components/         # UI components
│   │   ├── hooks/              # Custom React hooks
│   │   ├── services/           # API client
│   │   ├── App.tsx             # Main app entry
│   │   └── index.css           # Global styles
│   ├── package.json
│   └── vite.config.ts          # Vite configuration
│
├── backend/                     # FastAPI backend
│   ├── app/
│   │   ├── main.py             # FastAPI app
│   │   ├── config.py           # Configuration management
│   │   └── services/           # API integrations
│   ├── config/
│   │   └── system_prompt.txt   # AI system prompt
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── firebase.json                # Firebase Hosting config
├── dev.sh                       # Development script
├── package.json                 # Root scripts
└── README.md
```

## License

This project is licensed under the MIT License.
