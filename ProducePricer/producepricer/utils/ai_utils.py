import datetime
from producepricer import openai_client
from producepricer.models import AIResponse
from flask import jsonify
import logging
from producepricer import db

logger = logging.getLogger(__name__)

def get_ai_response(prompt=None, system_message=None, messages=None, model="gpt-3.5-turbo", response_format=None):
    """Get a response from OpenAI API with speed optimizations"""
    if system_message is None:
        system_message = "You are a helpful assistant for a produce pricing application."
    
    try:
        if messages is None:
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt or ""}
            ]
        
        # Check if content is too large and truncate
        max_tokens_per_message = 4000
        for msg in messages:
            if len(msg.get("content", "")) > max_tokens_per_message * 4:
                msg["content"] = msg["content"][:max_tokens_per_message*4] + "\n[Content truncated]"
        
        kwargs = {
            "model": model,  # Using gpt-3.5-turbo instead of gpt-4 (much faster)
            "messages": messages,
            "max_tokens": 2000,  # Limit response size
            "temperature": 0.3   # Lower temperature = faster, more predictable responses
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = openai_client.chat.completions.create(**kwargs)
        
        # Response handling code...
        if isinstance(response, dict):
            choices = response.get("choices")
            if choices and isinstance(choices, list) and "message" in choices[0]:
                content = choices[0]["message"]["content"]
            else:
                content = response.get("content", "")
        else:
            content = response.choices[0].message.content

        return {
            "success": True,
            "content": content
        }
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }