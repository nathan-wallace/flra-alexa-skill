import os
import json
import boto3
import feedparser
import requests
from datetime import datetime, timedelta

dynamo = boto3.resource('dynamodb')
feed_table = dynamo.Table(os.environ['FEED_TABLE'])
prefs_table = dynamo.Table(os.environ['PREFS_TABLE'])
comprehend_enabled = os.environ.get('COMPREHEND_ENABLED', 'false') == 'true'

comprehend = boto3.client('comprehend') if comprehend_enabled else None
secretsmanager = boto3.client('secretsmanager')
# Retrieve the skill ID from environment
ALEXA_SKILL_ID = os.environ.get('ALEXA_SKILL_ID', '')

# Secret name that stores LLM API key (and possibly Alexa OAuth token).
LLM_API_SECRET_NAME = os.environ['LLM_API_SECRET_NAME']

# Example feed list
MULTIPLE_FEEDS = [
    "https://www.flra.gov/feeds/decisions.xml",
    "https://www.flra.gov/feeds/press-releases.xml"
]

def lambda_handler(event, context):
    """
    1. Retrieve secrets (LLM API key, optional Alexa token).
    2. Fetch multiple RSS feeds, parse new items, call LLM to summarize.
    3. Store new items in DynamoDB with metadata.
    4. Check user preferences and trigger Proactive Notifications if needed.
    """
    secrets = get_secrets()
    llm_api_key = secrets.get("LLM_API_KEY", "")  # adjust to your secrets structure
    alexa_token = secrets.get("ALEXA_OAUTH_TOKEN", "")  # used for Proactive Events

    # 1) Process feeds
    new_items = []
    for rss_url in MULTIPLE_FEEDS:
        new_items.extend(process_feed(rss_url, llm_api_key))

    # 2) If new items, handle notifications
    if new_items:
        notify_users(new_items, alexa_token)

    return {"statusCode": 200, "body": f"Processed {len(new_items)} new items."}


def process_feed(rss_url, llm_api_key):
    feed_data = feedparser.parse(rss_url)
    entries = feed_data.entries
    new_items = []

    for entry in entries:
        item_id = entry.link
        if not item_exists(item_id):
            summary = summarize_text(entry.title, entry.description, llm_api_key)
            entities = detect_entities(entry.description) if comprehend else []

            feed_table.put_item(
                Item={
                    "ItemId": item_id,
                    "Title": entry.title,
                    "Link": entry.link,
                    "PublishedDate": getattr(entry, "published", str(datetime.utcnow())),
                    "Content": entry.description,
                    "Summary": summary,
                    "Entities": entities,
                    "FeedSource": rss_url,
                    "CreatedTimestamp": datetime.utcnow().isoformat()
                }
            )
            new_items.append({
                "ItemId": item_id,
                "Title": entry.title,
                "Link": entry.link,
                "Summary": summary,
                "PublishedDate": getattr(entry, "published", ""),
                "FeedSource": rss_url
            })

    return new_items


def item_exists(item_id):
    resp = feed_table.get_item(Key={"ItemId": item_id})
    return 'Item' in resp


def summarize_text(title, content, api_key):
    """
    Calls an LLM to generate bullet-point summaries.
    This example uses a hypothetical REST endpoint that requires an API key header.
    """
    prompt = f"""
    Summarize the following FLRA content in concise bullet points:
    Title: {title}
    Content: {content}
    Make it 3-5 bullet points highlighting key info.
    """

    # Suppose we also store the LLM endpoint in the secret or an environment variable
    # For demonstration, let's use an environment variable "LLM_ENDPOINT"
    llm_endpoint = os.environ.get("LLM_ENDPOINT", "https://api.example.com/v1/summarize")

    try:
        response = requests.post(
            llm_endpoint,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            },
            data=json.dumps({"prompt": prompt})
        )
        resp_json = response.json()
        return resp_json.get("summary", "No summary available.")
    except Exception as e:
        print("Error calling LLM:", e)
        return "Summary not available."


def detect_entities(content):
    try:
        resp = comprehend.detect_entities(Text=content, LanguageCode='en')
        entities = resp.get('Entities', [])
        return [{"Text": e["Text"], "Type": e["Type"]} for e in entities]
    except Exception as e:
        print("Error with Comprehend:", e)
        return []


def notify_users(new_items, alexa_token):
    """
    Check each user's preferences, see if we need to send them notifications.
    If a user has daily frequency, check last notification time and send once per day.
    If weekly, similarly. Filter items by user’s topic preference (e.g., press releases).
    Then call Alexa Proactive Events API.
    """
    # 1. Fetch all user preferences
    all_prefs = prefs_table.scan().get("Items", [])
    if not all_prefs:
        return

    for user_pref in all_prefs:
        user_id = user_pref["UserId"]
        frequency = user_pref.get("NotificationFrequency", "daily")
        topic = user_pref.get("PreferredTopic", "decisions")
        last_notified = user_pref.get("LastNotifiedTimestamp", None)

        # Check if user is due for notifications
        if not is_user_due_for_notification(frequency, last_notified):
            continue

        # Filter new_items by topic (if feed source or summary matches “press-releases”).
        filtered_items = []
        for item in new_items:
            if topic in item["FeedSource"]:
                filtered_items.append(item)

        if filtered_items:
            # Trigger Alexa Proactive Notification
            send_proactive_notification(user_id, filtered_items, alexa_token)

            # Update last notified
            prefs_table.update_item(
                Key={"UserId": user_id},
                UpdateExpression="SET LastNotifiedTimestamp = :ts",
                ExpressionAttributeValues={":ts": datetime.utcnow().isoformat()}
            )


def is_user_due_for_notification(frequency, last_notified):
    """
    If frequency = daily, user is due if they haven't been notified in 24+ hours.
    If weekly, user is due if they haven't been notified in 7+ days.
    """
    if not last_notified:
        return True

    last_dt = datetime.fromisoformat(last_notified)
    now = datetime.utcnow()
    if frequency == "daily":
        return (now - last_dt) >= timedelta(days=1)
    elif frequency == "weekly":
        return (now - last_dt) >= timedelta(days=7)
    else:
        # default daily
        return (now - last_dt) >= timedelta(days=1)


def send_proactive_notification(user_id, items, alexa_token):
    """
    Calls the Alexa Proactive Events API with a simple notification about new FLRA updates.
    In practice, you need a valid LWA token to authenticate. 
    The user must have enabled skill notifications.
    """
    if not alexa_token:
        print("No Alexa OAuth token found, skipping proactive notification.")
        return

    # Construct the event payload (simplified). See official docs for full schema:
    # https://developer.amazon.com/en-US/docs/alexa/notifications/notify-users.html
    event_payload = {
        "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "referenceId": f"FLRAUpdate-{datetime.utcnow().timestamp()}",
        "expiryTime": (datetime.utcnow() + timedelta(hours=1)).replace(microsecond=0).isoformat() + "Z",
        "event": {
            "name": "AMAZON.MessageAlert.Activated",
            "payload": {
                "state": {
                    "status": "UNREAD",
                    "freshness": "NEW"
                },
                "messageGroup": {
                    "creator": {
                        "name": "FLRA Bot"
                    },
                    "count": len(items),
                    "urgency": "URGENT"
                }
            }
        },
        "relevantAudience": {
            "type": "Unicast",
            "payload": {
                # The user’s Alexa user ID is not typically the same as "UserId" from your table
                # You need the correct ID. This is an illustrative example.
                "user": user_id
            }
        }
    }

    try:
        proactive_api_url = f"https://api.amazonalexa.com/v1/proactiveEvents/stages/development"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {alexa_token}"
        }
        r = requests.post(proactive_api_url, headers=headers, data=json.dumps(event_payload))
        if r.status_code >= 300:
            print("Proactive notification failed:", r.text)
        else:
            print("Proactive notification sent successfully.")
    except Exception as e:
        print("Exception sending proactive notification:", e)


def get_secrets():
    """
    Retrieve JSON secrets from AWS Secrets Manager.
    Expecting a JSON structure like:
    {
      "LLM_API_KEY": "...",
      "ALEXA_OAUTH_TOKEN": "..."
    }
    """
    try:
        resp = secretsmanager.get_secret_value(SecretId=LLM_API_SECRET_NAME)
        if 'SecretString' in resp:
            return json.loads(resp['SecretString'])
        else:
            # If the secret is in binary form
            return json.loads(resp['SecretBinary'])
    except Exception as e:
        print("Error retrieving secrets:", e)
        return {}
