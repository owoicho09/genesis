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
@api_view(["POST"])
def run_genesis_agent(request):
    print('---hitting---')

    try:
        if "type" in request.data and "args" in request.data:
            intent_type = request.data["type"]
            args = request.data["args"]
            input_text = args.get("input", "")

            # Convert structured input into clearer NL for LLM
            type_to_prompt = {
                "google_scrape": f"Scrape Google Maps for {input_text}",
                "instagram_scrape": f"Scrape Instagram for {input_text}",
                "send_email": f"Send an email to {input_text}",
                "send_outreach": f"Send outreach to {input_text}",
                "warmup_emails": f"Warm up email inboxes",
                "launch_campaign": f"Launch a campaign for {input_text}",

                # Add more types as needed
            }

            nl_input = type_to_prompt.get(intent_type, input_text)

            initial_state = {
                "user_input": nl_input  # let the LLM process a clearer sentence
            }

        else:
            user_input = request.data.get("user_input", "")
            if not user_input:
                return Response({"error": "user_input is required"}, status=400)

            initial_state = {"user_input": user_input}

        result = campaign_agent_executor.invoke(initial_state)
        final_result = result.get("result", "⚠️ No response generated")

        return Response({"result": final_result}, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ API Error: {e}")
        print(traceback.format_exc())  # ⬅️ This gives full details in Render logs
        return Response({"error": str(e)}, status=500)



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
