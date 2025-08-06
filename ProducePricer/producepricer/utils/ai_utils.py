import datetime
from producepricer import openai_client
from producepricer.models import AIResponse
from flask import jsonify
import logging
from producepricer import db

logger = logging.getLogger(__name__)

def get_ai_response(prompt, system_message=None):
    """Get a response from OpenAI API"""
    if system_message is None:
        system_message = "You are a helpful assistant for a produce pricing application. Your goal is to provide data driven insights and summaries based on the provided information."
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800
        )

        # save the response to the database
        # summary = response.choices[0].message.content
        # ai_response = AIResponse(content=summary, date=datetime.utcnow())
        # db.session.add(ai_response)
        # db.session.commit()

        return {
            "success": True,
            "content": response.choices[0].message.content
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }