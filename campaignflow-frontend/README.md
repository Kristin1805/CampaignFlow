# CampaignFlow Frontend
Frontend for CampaignFlow, built with Vite and vanilla JavaScript (HTML/CSS).
It communicates with the Django backend API.

## Requirements
- Node.js 24+ (провери с `node -v`)

## Setup
1. Clone the repository:
   `git clone https://github.com/Kristin1805/CampaignFlow.git`
2. Go to the frontend folder:
   `cd CampaignFlow/campaignflow-frontend`
3. Install dependencies:
   `npm install`
4. Create your local env file by copying `.env.example` to `.env`

## Run
`npm run dev`

Open http://localhost:5173/

## Build
`npm run build`
Creates the production files in `dist/`.

`npm run preview`
Runs the production build locally for testing.

## Environment variables
- Copy `.env.example` to `.env` for local settings.
- Do not commit `.env` (it is ignored by Git).
- Only variables starting with `VITE_` are available in frontend code.
- Never put secrets (passwords, API keys) in `VITE_` variables, they are visible in the browser.

## API proxy
Requests starting with `/api` are forwarded by Vite to the Django backend
at `http://127.0.0.1:8000` (configured in `vite.config.js`).

The Django server must be running for API requests to work:
`python manage.py runserver`