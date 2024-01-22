from openai import OpenAI
from utils.digit_utils import (
    get_auth_token, 
    file_complaint, 
    search_complaint
)
from utils.openai_utils import (
    create_thread,
    upload_message,
    get_run_status,
    get_assistant_message,
    create_assistant,
    transcribe_audio,
)
from utils.redis_utils import (
    get_redis_value,
    set_redis,
)

from utils.bhashini import (
    bhashini_input,
    bhashini_output,
)

import json
import time
import os

from dotenv import load_dotenv

load_dotenv(
    dotenv_path="ops/.env",
)

openai_api_key = os.getenv("OPENAI_API_KEY")

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

assistant_id = get_redis_value("assistant_id")
print(assistant_id)

client = OpenAI(
    api_key=openai_api_key,
)

assistant = create_assistant(client, assistant_id)

def chat(chat_id, input_message):
    history = get_redis_value(chat_id)
    if history == None:
        history = {
            "thread_id": None,
            "run_id": None,
            "status": None,
        }
    else:
        history = json.loads(history)
    thread_id = history.get("thread_id")
    run_id = history.get("run_id")
    status = history.get("status")

    try:
        run = client.beta.threads.runs.retrieve(thread_id, run_id)
    except Exception as e:
        run = None
    try:
        thread = client.beta.threads.retrieve(thread_id)
    except Exception as e:
        thread = create_thread(client)

    if status == "completed" or status == None:

        # For some specific Indian languages like Tamil, Marathi, Kannada , Bhashini API works better than Google Translate API
        '''Supported languages are : Assamese, Bengali, Bodo, Dogri, English, Gujarati, Hindi, Kannada, Kashmiri, Konkani, Maithili, Malayalam, 
        Manipuri, Marathi, Nepali, Odia, Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu, Urdu'''
        # Assuming original input is in Punjabi, translating into English using Bhashini API
        translated_message = bhashini_input(input_message)
        run = upload_message(client, thread.id, translated_message, assistant.id)
        run, status = get_run_status(run, client, thread)

        output_message = get_assistant_message(client, thread.id)
        assistant_message = bhashini_output(output_message)

        history = {
            "thread_id": thread.id,
            "run_id": run.id,
            "status": status,
        }
        history = json.dumps(history)
        set_redis(chat_id, history)
    
    if status == "requires_action":
        if run:
            tools_to_call = run.required_action.submit_tool_outputs.tool_calls
        else:
            run, status = get_run_status(run, client, thread)
            tools_to_call = run.required_action.submit_tool_outputs.tool_calls

        for tool in tools_to_call:
            username = USERNAME
            auth_token = get_auth_token(
                {
                    "username": username,
                    "password": PASSWORD
                }
            )
            func_name = tool.function.name
            print(f"Function name: {func_name}")
            parameters = json.loads(tool.function.arguments)
            parameters["auth_token"] = auth_token
            parameters["username"] = username
            print(f"Parameters: {parameters}")

            tool_output_array = []

            if func_name == "raise_complaint":
                complaint = file_complaint(parameters)
                if complaint:
                    tool_output_array.append(
                        {
                            "tool_call_id": tool.id,
                            "output": complaint["ServiceWrappers"][0]["service"]["serviceRequestId"]
                        }
                    )
                    run = client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread.id,
                        run_id=run.id,
                        tool_outputs=tool_output_array
                    )
                    run, status = get_run_status(run, client, thread)

                    message = get_assistant_message(client, thread.id)
                    # translating English to Punjabi using Bhashini API
                    # message = bhashini_output(message)

                    history = {
                        "thread_id": thread.id,
                        "run_id": run.id,
                        "status": status,
                    }
                    history = json.dumps(history)
                    set_redis(chat_id, history)
                    return message, history
                else:
                    return "Complaint failed", history
                
            elif func_name == "search_complaint":
                complaint = search_complaint(parameters)
                if complaint:
                    tool_output_array.append(
                        {
                            "tool_call_id": tool.id,
                            "output": complaint["ServiceWrappers"][0]["service"]["applicationStatus"]
                        }
                    )
                    run = client.beta.threads.runs.submit_tool_outputs(
                        thread_id=thread.id,
                        run_id=run.id,
                        tool_outputs=tool_output_array
                    )
                    run, status = get_run_status(run, client, thread)

                    message = get_assistant_message(client, thread.id)
                    # translating English to Punjabi using Bhashini API
                    # message = bhashini_output(message)
                    
                    history = {
                        "thread_id": thread.id,
                        "run_id": run.id,
                        "status": status,
                    }
                    history = json.dumps(history)
                    set_redis(chat_id, history)
                    return message, history
                else:
                    return "Complaint not found", history
                
    return assistant_message, history

def audio_chat(chat_id, audio_file):
    input_message = transcribe_audio(audio_file, client)
    print(f"The input message is : {input_message}")
    assistant_message, history =  chat(chat_id, input_message)
    return assistant_message, history

