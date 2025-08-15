import datetime
from producepricer import openai_client
from producepricer.models import AIResponse
from flask import jsonify
import logging
from producepricer import db

logger = logging.getLogger(__name__)

def get_ai_response(prompt=None, system_message=None, messages=None, model="gpt-4-turbo-preview", response_format=None):
    """Get a response from OpenAI API"""
    if system_message is None:
        system_message = "You are a helpful assistant for a produce pricing application. Your goal is to provide data driven insights and summaries based on the provided information."
    
    try:
        if messages is None:
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt or ""}
            ]
        kwargs = {
            "model": model,
            "messages": messages
            #"max_tokens": 2048
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = openai_client.chat.completions.create(**kwargs)
        # Debug: print type and content
        print("OpenAI raw response:", response)

        # If response is a dict (old API or mock), handle accordingly
        if isinstance(response, dict):
            # Try to get content from dict structure
            choices = response.get("choices")
            if choices and isinstance(choices, list) and "message" in choices[0]:
                content = choices[0]["message"]["content"]
            else:
                # Fallback: try to get content directly
                content = response.get("content", "")
        else:
            # New OpenAI object API
            content = response.choices[0].message.content

        return {
            "success": True,
            "content": content
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }