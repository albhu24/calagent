from datetime import datetime
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pydantic_ai import Agent, RunContext, ModelRetry
import requests
from googleapiclient.errors import HttpError
import redis




api_key = os.getenv("OPENAI_API_KEY")
redis_pw = os.getenv("REDIS_PASS")
redis_host = os.getenv("REDIS_HOST")
calendar_id = os.getenv("CAL_ID")

# Path to your service account key file
SERVICE_ACCOUNT_FILE = "credentials.json"
# Define the scope for Google Calendar
SCOPES = ['https://www.googleapis.com/auth/calendar']
# Authenticate using the service account
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
# Build the Calendar API client
service = build('calendar', 'v3', credentials=credentials)
# ID of the calendar to access (use 'primary' for the default calendar)
calendar_id = 'albhu24@gmail.com'


agent = Agent('openai:gpt-4o',system_prompt=
              f"""You are an personal assistant that specializes in calendars and scheduling. 
              When using the date and time as arguments for tools, convert the date and time into ISO 8601 format first. You can assume that today's date is {datetime.now().isoformat()}
              If you are unsure with how to proceed with a task, be sure to ask any clarifying questions for additional input.
              Based on the inputs receieved, use the correct function(s) (if needed) to help with the task.""")


# Export calendar_id, password, host

redis_DB = redis.Redis(
    host=redis_host,
    port=11299,
    decode_responses=True,
    username="default",
    password=redis_pw,
)


@agent.tool(retries=2)
async def get_events_from_timeperiod(ctx: RunContext[str], startDateTime: str, endDateTime: str)-> dict:
    # Should limit the timeperiod to a specified length. 
    try: 
        events_result = service.events().list(
            calendarId=calendar_id, timeMin=startDateTime,
            maxResults=5, singleEvents=True,
            timeMax=endDateTime,
            orderBy='startTime').execute()
        
        events = events_result.get('items', [])
        if not events:
            return {}
        else:
            d = {}
            for event in events:
                d[f"{event["summary"]}"] = {}
                d[f"{event["summary"]}"]['startDate'] = event['start']['date'] if 'date' in event['start'] else event['start']['dateTime']
                d[f"{event["summary"]}"]['endDate'] = event['end']['date'] if 'date' in event['end'] else event['end']['dateTime']
                d[f"{event["summary"]}"]['location'] = event['location'] if 'location' in event else 'N/A'
        return d
    
    except HttpError as http_err:
        raise ModelRetry(
                f'It looks like an {http_err} has occurred, would you like me to try again?'
            )
    except Exception as e:
        raise ModelRetry(
                f'It looks like an unexpected error has occured, would you like me to try again?'
            )
    
    
@agent.tool
async def create_event(ctx: RunContext[str], summary, location, description, startDateTime, endDateTime)-> str:
    event = {
        'summary': summary or None,
        'location': location or None,
        'description': description or None,
        'start': {
            'dateTime': startDateTime or None,
            'timeZone': 'America/Los_Angeles',
        },
        'end': {
            'dateTime': endDateTime or None,
            'timeZone': 'America/Los_Angeles',
        }
    }
    try:
        if redis_DB.exists(summary):
            raise ModelRetry(
                f'{summary} already exists in your events. Use another name!'
            )
        insertResult = service.events().insert(calendarId=calendar_id, body=event).execute()
        redis_DB.set('location', insertResult.id)

        return insertResult
    except HttpError as http_err:
        raise ModelRetry(
                f'It looks like an {http_err} has occurred, would you like me to try again?'
            )
    except Exception as e:
        raise ModelRetry(
                f'It looks like an unexpected error has occured, would you like me to try again?'
            )

@agent.tool
async def delete_event(ctx: RunContext[str], eventName)-> str:
    # What if we are vague about eventName?
    try:
        eventID = redis_DB.get(eventName)
        if not eventID:
            raise ModelRetry(
                f'{eventName} is not an entry in your calendar!'
            )
        service.events().delete(calendarId=calendar_id, eventId=eventID).execute()
        return f'Deleted {eventName}!'
    
    except HttpError as http_err:
        raise ModelRetry(
                f'It looks like an {http_err} has occurred, would you like me to try again?'
            )
    except Exception as e:
        raise ModelRetry(
                f'It looks like an unexpected error has occured, would you like me to try again?'
            )


@agent.tool
async def update_event(ctx: RunContext[str], eventName, summary, location, description, startDateTime, endDateTime)-> dict:

    try:
        eventID = redis_DB.get(eventName)
        if not eventID:
            raise ModelRetry(
                f'{eventName} is not an entry in your calendar!'
            )
        og_event = service.events().get(calendarId=calendar_id, eventId=eventID).execute()
        og_event['summary'] = summary

        updated_event = service.events().update(calendarId=calendar_id, eventId=eventID, body=og_event).execute()
        return updated_event
    
    except HttpError as http_err:
        raise ModelRetry(
                f'It looks like an {http_err} has occurred, would you like me to try again?'
            )
    except Exception as e:
        raise ModelRetry(
                f'It looks like an unexpected error has occured, would you like me to try again?'
            )

def main():
    while True:
        user_input = input("Enter the input here: ")
        if (user_input == "exit()"):
            break
        result_sync = agent.run_sync(user_input)
        print(result_sync.data)

main()
    








