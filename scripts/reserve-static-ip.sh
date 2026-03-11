#!/bin/bash
# Reserve a static external IP in GCP for the AI Assistant VM
# Run this from GCP Cloud Shell or a machine with gcloud configured
#
# Usage: bash scripts/reserve-static-ip.sh [PROJECT_ID]
set -e

PROJECT_ID="${1:-$(gcloud config get-value project)}"
REGION="asia-southeast1"
ZONE="asia-southeast1-b"
IP_NAME="ai-assistant-ip"
INSTANCE_NAME="instance-20260306-035055"

echo "=== Reserve Static IP for AI Assistant ==="
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo "VM:      $INSTANCE_NAME"
echo ""

# Step 1: Get current ephemeral IP
CURRENT_IP=$(gcloud compute instances describe "$INSTANCE_NAME" \
  --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)' \
  --project="$PROJECT_ID")
echo "Current ephemeral IP: $CURRENT_IP"

# Step 2: Promote the ephemeral IP to static
echo ""
echo "Promoting $CURRENT_IP to static IP '$IP_NAME'..."
gcloud compute addresses create "$IP_NAME" \
  --addresses="$CURRENT_IP" \
  --region="$REGION" \
  --project="$PROJECT_ID"

echo ""
echo "Static IP reserved: $CURRENT_IP as '$IP_NAME'"
echo ""
echo "The VM will now keep this IP across restarts."
echo "No DNS or webhook changes needed since the IP stays the same."
echo ""
echo "To verify: gcloud compute addresses list --project=$PROJECT_ID"
echo "Cost: ~\$0.004/hr when attached to a running VM (free while VM is running)"
