import os
import boto3
import random
from datetime import datetime

feed_table_name = os.environ['FEED_TABLE']
prefs_table_name = os.environ['PREFS_TABLE']

dynamo = boto3.resource('dynamodb')
feed_table = dynamo.Table(feed_table_name)
prefs_table = dynamo.Table(prefs_table_name)

cloudwatch = boto3.client('cloudwatch', region_name="us-east-1")  # or your region

def lambda_handler(event, context):
    """
    Main Alexa Skill entry point.
    """
    # [1] Record an invocation metric
    put_custom_metric("SkillInvocationCount", 1)

    if "request" not in event:
        return build_plaintext_response("Invalid request.")

    request_type = event["request"]["type"]

    if request_type == "LaunchRequest":
        return on_launch(event)
    elif request_type == "IntentRequest":
        return on_intent(event["request"])
    else:
        return build_plaintext_response("Sorry, I didn't understand that.")

def on_launch(event):
    speech_text = "Welcome to the FLRA Bot. You can ask for the latest updates or set your preferences."
    return build_apl_response(
        speech_text,
        "Welcome to FLRA Bot",
        "Ask for the latest FLRA decisions or press releases."
    )

def on_intent(request):
    intent_name = request["intent"]["name"]

    # [2] Record an intent metric
    put_custom_metric(f"{intent_name}Count", 1)

    if intent_name == "GetLatestUpdatesIntent":
        return handle_get_latest_updates(request)
    elif intent_name == "SetPreferenceIntent":
        return handle_set_preference(request)
    elif intent_name == "GetPreferenceIntent":
        return handle_get_preference(request)
    elif intent_name == "PlayAudioIntent":
        return handle_play_audio(request)
    else:
        return build_plaintext_response("I don't know that intent.")

def handle_get_latest_updates(request):
    user_id = get_alexa_user_id(request)
    user_prefs = load_user_preferences(user_id)

    # Filter by user topic preference if desired
    topic = user_prefs.get("PreferredTopic", "decisions")

    # Query feed table for items that match the topic (simple filter on FeedSource or Title)
    resp = feed_table.scan()
    items = resp.get("Items", [])

    # Filter items by topic
    filtered = [it for it in items if topic in it.get("FeedSource", "")]
    # Sort by CreatedTimestamp desc
    items_sorted = sorted(filtered, key=lambda x: x["CreatedTimestamp"], reverse=True)
    latest_items = items_sorted[:3]  # top 3

    if not latest_items:
        return build_plaintext_response(f"No new {topic} updates at this time.")

    # Construct speech from bullet-point summary
    speech_text = f"Here are the latest {topic} updates:\n"
    for i, item in enumerate(latest_items):
        speech_text += f"Update {i+1}: {item.get('Title')}. "
        speech_text += f"Summary: {item.get('Summary')}\n"

    return build_apl_response(
        speech_text,
        "Latest FLRA Updates",
        speech_text  # This will also show in APL
    )

def handle_set_preference(request):
    user_id = get_alexa_user_id(request)
    intent_slots = request["intent"]["slots"]
    frequency = intent_slots.get("frequency", {}).get("value", "daily")
    topic = intent_slots.get("topic", {}).get("value", "decisions")

    prefs_table.put_item(
        Item={
            "UserId": user_id,
            "NotificationFrequency": frequency,
            "PreferredTopic": topic,
            "UpdatedTimestamp": datetime.utcnow().isoformat()
        }
    )

    return build_plaintext_response(f"Got it. Preference set to {frequency} updates for {topic}.")

def handle_get_preference(request):
    user_id = get_alexa_user_id(request)
    user_prefs = load_user_preferences(user_id)

    if not user_prefs:
        return build_plaintext_response("I don't have any preferences for you yet.")
    freq = user_prefs.get("NotificationFrequency", "daily")
    topic = user_prefs.get("PreferredTopic", "decisions")
    return build_plaintext_response(f"Your preference is {freq} updates about {topic}.")

def handle_play_audio(request):
    """
    Demonstration of sending an AudioPlayer directive.
    For example, playing a short audio clip. 
    Make sure your skill is set to the 'Music & Audio' category or has permissions to use AudioPlayer.
    """
    audio_url = "https://your-audio-file-host/audio-sample.mp3"
    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": "Playing the requested audio..."
            },
            "directives": [
                {
                    "type": "AudioPlayer.Play",
                    "playBehavior": "REPLACE_ALL",
                    "audioItem": {
                        "stream": {
                            "token": "some-audio-token",
                            "url": audio_url,
                            "offsetInMilliseconds": 0
                        }
                    }
                }
            ],
            "shouldEndSession": True
        }
    }

def get_alexa_user_id(request):
    # Typically available in session->user->userId
    # For demonstration, we store it in the intent request or fallback to "demoUser"
    return request.get("user", {}).get("userId", "demoUser")

def load_user_preferences(user_id):
    resp = prefs_table.get_item(Key={"UserId": user_id})
    return resp.get("Item", {})

def put_custom_metric(metric_name, value):
    """
    Send a custom metric to CloudWatch. For example:
    - SkillInvocationCount
    - GetLatestUpdatesIntentCount
    """
    try:
        cloudwatch.put_metric_data(
            Namespace="FLRAAlexaSkill",
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Timestamp": datetime.utcnow(),
                    "Value": value,
                    "Unit": "Count"
                }
            ]
        )
    except Exception as e:
        print("Failed to put custom metric:", e)

#######################
# RICH RESPONSES
#######################

def build_plaintext_response(speech_text, end_session=False):
    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": speech_text
            },
            "shouldEndSession": end_session
        }
    }

def build_apl_response(speech_text, title, subtitle, end_session=False):
    """
    Returns a response that includes an APL directive for devices with screens.
    For devices without screens, Alexa will simply speak the text.
    """
    # Minimal example APL content
    apl_document = {
        "type": "APL",
        "version": "1.7",
        "import": [
            {
                "name": "alexa-layouts",
                "version": "1.3.0"
            }
        ],
        "mainTemplate": {
            "parameters": [
                "payload"
            ],
            "item": {
                "type": "Container",
                "items": [
                    {
                        "type": "Text",
                        "text": title,
                        "style": "textStylePrimary1"
                    },
                    {
                        "type": "Text",
                        "text": subtitle,
                        "style": "textStylePrimary2"
                    }
                ]
            }
        }
    }

    return {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": speech_text
            },
            "card": {
                "type": "Simple",
                "title": title,
                "content": subtitle
            },
            "directives": [
                {
                    "type": "Alexa.Presentation.APL.RenderDocument",
                    "document": apl_document,
                    "datasources": {}
                }
            ],
            "shouldEndSession": end_session
        }
    }
