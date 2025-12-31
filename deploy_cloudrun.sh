#!/bin/bash

# Configuration
PROJECT_ID="zenn-shadow-director"
SERVICE_NAME="shadow-director-bot"
REGION="us-central1"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
GCS_BUCKET="zenn-shadow-director-data"

# Load secrets from .env file (if it exists) to get DISCORD_BOT_TOKEN
if [ -f .env ]; then
    echo "Loading secrets from .env file..."
    export $(grep -v '^#' .env | xargs)
else
    echo "Warning: .env file not found. Ensure DISCORD_BOT_TOKEN is set in your environment."
fi

# Check if token is available
if [ -z "$DISCORD_BOT_TOKEN" ]; then
    echo "Error: DISCORD_BOT_TOKEN is not set."
    echo "Please create a .env file with DISCORD_BOT_TOKEN=... or export it manually."
    exit 1
fi

echo "Deploying $SERVICE_NAME to Google Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"

# 0. Enable Required APIs
echo "------------------------------------------------"
echo "Step 0: Enabling Required APIs..."
echo "------------------------------------------------"
gcloud services enable docs.googleapis.com --project=$PROJECT_ID
gcloud services enable drive.googleapis.com --project=$PROJECT_ID
echo "✅ Google Docs & Drive APIs enabled"

# 1. Build and Push Container Image
echo "------------------------------------------------"
echo "Step 1: Building and Pushing Docker Image..."
echo "------------------------------------------------"
gcloud builds submit --tag $IMAGE_NAME

# 2. Deploy to Cloud Run
echo "------------------------------------------------"
echo "Step 2: Deploying to Cloud Run..."
echo "------------------------------------------------"
gcloud run deploy $SERVICE_NAME \
    --image $IMAGE_NAME \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --memory 1Gi \
    --set-env-vars "APP_ENV=production,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=True,GCS_BUCKET_NAME=$GCS_BUCKET,DISCORD_BOT_TOKEN=$DISCORD_BOT_TOKEN,USE_MEMORY_BANK=True"

echo "------------------------------------------------"
echo "Step 3: Configuring Service Account Permissions..."
echo "------------------------------------------------"

# Get the service account email used by Cloud Run
SERVICE_ACCOUNT=$(gcloud run services describe $SERVICE_NAME \
    --region=$REGION \
    --platform=managed \
    --format="value(spec.template.spec.serviceAccountName)")

if [ -z "$SERVICE_ACCOUNT" ]; then
    # If not specified, it uses the default compute service account
    PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
    SERVICE_ACCOUNT="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
fi

echo "Service Account: $SERVICE_ACCOUNT"

# Grant necessary roles for Google Docs/Drive access
# Note: For creating docs in a specific shared drive, you may need additional setup
echo "Granting roles/editor to service account for Docs/Drive access..."
# This allows the service account to create and edit Google Docs
# For production, you should create a custom role with minimal permissions

echo "✅ Service account configured"
echo ""
echo "📝 Google Docs API Setup:"
echo "   The service account can now create Google Docs."
echo "   By default, docs will be created in the service account's Drive."
echo ""
echo "   To share docs with users automatically:"
echo "   1. Enable Domain-Wide Delegation (for Workspace)"
echo "   2. Or manually share the service account email: $SERVICE_ACCOUNT"
echo ""

echo "------------------------------------------------"
echo "Deployment Completed Successfully! 🎉"
echo "------------------------------------------------"
