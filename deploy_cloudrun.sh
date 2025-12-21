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
    --set-env-vars "APP_ENV=production,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=True,GCS_BUCKET_NAME=$GCS_BUCKET,DISCORD_BOT_TOKEN=$DISCORD_BOT_TOKEN"

echo "------------------------------------------------"
echo "Deployment Initiated Successfully."
echo "------------------------------------------------"
