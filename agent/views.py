from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from userauth.models import User, Profile
from . import serializers
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
# views.py
from django.http import HttpResponse
from django.utils.timezone import now
# core/api/views.py or wherever your API views live
from urllib.parse import unquote
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from agent.tools.langgraph import campaign_agent_executor  # <-- Your compiled LangGraph
from agent.tools.langgraph import CampaignAgentState  # TypedDict
from .models import *
from django.contrib.auth import get_user_model
from django.http import JsonResponse

import json
import traceback  # ✅ Add this import at the top



# Create your views here.
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = serializers.MyTokenObtainPairSerializer


User = get_user_model()


@method_decorator(csrf_exempt, name='dispatch')
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [AllowAny]    # allow any user to access this view
    serializer_class = serializers.RegisterSerializer




def chatbot_page(request):
    return render(request, "chatbot/index.html", {
        'GENESIS_API_URL': settings.SITE_URL
    })



@csrf_exempt
def run_genesis_agent(request):
    print('---hitting---')

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        # ✅ Parse JSON from request.body instead of request.data
        data = json.loads(request.body)

        if "type" in data and "args" in data:
            intent_type = data["type"]
            args = data["args"]
            input_text = args.get("input", "")

            type_to_prompt = {
                "google_scrape": f"Scrape Google Maps for {input_text}",
                "instagram_scraping": f"Scrape Instagram for {input_text}",
                "send_email": f"Send an email to {input_text}",
                "send_outreach": f"Send outreach to {input_text}",
                "followup_outreach": f"Send followup outreach to {input_text}",
                "warmup_emails": f"Warm up email inboxes",
                "launch_campaign": f"Launch a campaign for {input_text}",
            }

            nl_input = type_to_prompt.get(intent_type, input_text)
            initial_state = {"user_input": nl_input}
        else:
            user_input = data.get("user_input", "")
            if not user_input:
                return JsonResponse({"error": "user_input is required"}, status=400)
            initial_state = {"user_input": user_input}

        result = campaign_agent_executor.invoke(initial_state)
        final_result = result.get("result", "⚠️ No response generated")

        return JsonResponse({"result": final_result}, status=200)

    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}")
        print(traceback.format_exc())
        return JsonResponse({"error": "Invalid JSON in request body"}, status=400)

    except Exception as e:
        print(f"❌ API Error: {e}")
        print(traceback.format_exc())  # ✅ Now this will work
        return JsonResponse({"error": str(e)}, status=500)

def health_check(request):
    return JsonResponse({"status": "ok"})

def email_open_view(request, email):
    print("📩 Tracking pixel hit!")
    print(f"📧 Raw email from URL: {email}")

    # Decode URL-encoded email (e.g., michael+promo@email.com)
    email = unquote(email)
    print(f"📧 Decoded email: {email}")

    try:
        lead = Lead.objects.get(email=email)
        print(f"✅ Found lead: {lead}")

        if not lead.opened:
            lead.opened = True
            lead.opened_at = timezone.now()
            lead.save()
            print(f"🟢 Marked as opened at {lead.opened_at}")
        else:
            print("ℹ️ Lead already marked as opened.")

    except Lead.DoesNotExist:
        print("❌ Lead not found in DB.")

    # Return 1x1 transparent gif
    pixel = (
        b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xFF\xFF\xFF!'
        b'\xF9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01'
        b'\x00\x00\x02\x02D\x01\x00;'
    )

    print("📤 Returning tracking pixel.\n")
    return HttpResponse(pixel, content_type='image/gif')
