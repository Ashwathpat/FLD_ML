#!/usr/bin/env bash
# scripts/drill.sh
# Failover Drill Script — FLD-Screen
# Measures RTO (Recovery Time Objective) and RPO (Recovery Point Objective).
#
# Usage:
#   ./scripts/drill.sh <public_hostname> <aws_sg_id> [--restore]
#
# Prerequisites:
#   - AWS CLI configured with access to the security group
#   - 'jq' installed
#   - The DB write loop from drill_rpo_seed.sh should be running in parallel

set -euo pipefail

HOSTNAME="${1:?Usage: $0 <public_hostname> <aws_sg_id>}"
SG_ID="${2:?Missing security group ID}"
RESTORE="${3:-}"

DRILL_LOG="drill_results_$(date +%Y%m%d_%H%M%S).txt"

echo "=== FLD-Screen Failover Drill ===" | tee "$DRILL_LOG"
echo "Hostname  : $HOSTNAME"             | tee -a "$DRILL_LOG"
echo "SG ID     : $SG_ID"               | tee -a "$DRILL_LOG"
echo "Start time: $(date -u +%FT%TZ)"   | tee -a "$DRILL_LOG"

# ── Restore mode ─────────────────────────────────────────────────────────────
if [ "$RESTORE" = "--restore" ]; then
    echo "[restore] Re-opening port 443 in $SG_ID ..."
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp --port 443 --cidr 0.0.0.0/0 2>/dev/null || true
    echo "[restore] Done."
    exit 0
fi

# ── Record last row written before outage ────────────────────────────────────
LAST_AWS_TIMESTAMP=$(date -u +%FT%TZ)
echo "RPO reference timestamp (before outage): $LAST_AWS_TIMESTAMP" | tee -a "$DRILL_LOG"

# ── Simulate outage: remove HTTPS from AWS SG ────────────────────────────────
echo "[drill] Blocking HTTPS on $SG_ID ..." | tee -a "$DRILL_LOG"
aws ec2 revoke-security-group-ingress \
    --group-id "$SG_ID" \
    --protocol tcp --port 443 --cidr 0.0.0.0/0
OUTAGE_START=$(date +%s)

# ── Poll until Azure serves the request ──────────────────────────────────────
echo "[drill] Polling https://$HOSTNAME/readyz ..." | tee -a "$DRILL_LOG"
AZURE_RESPONSE_TIME=""
for i in $(seq 1 120); do
    SERVED_BY=$(curl -s -m 5 -o /dev/null -w "%{http_code}" \
        -H "User-Agent: drill-script" \
        "https://$HOSTNAME/readyz" 2>/dev/null || echo "000")
    HDR=$(curl -sI -m 5 "https://$HOSTNAME/readyz" 2>/dev/null | grep -i x-served-by | tr -d '\r' || echo "")
    if echo "$HDR" | grep -iq "azure"; then
        AZURE_RESPONSE_TIME=$(date +%s)
        echo "[drill] Azure responded at poll #$i — $HDR" | tee -a "$DRILL_LOG"
        break
    fi
    sleep 1
done

# ── Compute RTO ───────────────────────────────────────────────────────────────
if [ -n "$AZURE_RESPONSE_TIME" ]; then
    RTO=$((AZURE_RESPONSE_TIME - OUTAGE_START))
    echo "RTO = ${RTO}s" | tee -a "$DRILL_LOG"
else
    echo "RTO = TIMEOUT (Azure never responded within 2 minutes)" | tee -a "$DRILL_LOG"
fi

# ── Restore immediately ───────────────────────────────────────────────────────
echo "[drill] Restoring HTTPS ingress ..." | tee -a "$DRILL_LOG"
aws ec2 authorize-security-group-ingress \
    --group-id "$SG_ID" \
    --protocol tcp --port 443 --cidr 0.0.0.0/0 2>/dev/null || true

echo "Drill end: $(date -u +%FT%TZ)"  | tee -a "$DRILL_LOG"
echo "Results saved to $DRILL_LOG"
