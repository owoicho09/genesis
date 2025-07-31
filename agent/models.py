from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.db import transaction
from shortuuid.django_fields import ShortUUIDField
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta
from cloudinary import uploader
import cloudinary
from cloudinary.models import CloudinaryField



PLATFORM_CHOICES = [
        ('meta', 'Meta (Facebook/Instagram)'),
        ('tiktok', 'TikTok'),
        ('google', 'Google Ads'),
        ('x', 'Twitter/X'),
        ('others', 'Others'),
    ]

CREATIVE_CHOICES = [
    ("image", "Image"),
    ("video", "Video"),
    ("carousel", "Carousel"),
    ("audio", "Audio"),
    ("text", "Text"),
    ("story", "Story"),
    ("reel", "Reel"),
    ("adset", "Adset"),
    ("ad", "Ad"),
    ("adgroup", "Adgroup"),
    ("adset", "Adset"),

]

STATUS_CHOICES = [
    ("pending", "Pending"),
    ("paused", "Paused"),
    ("active", "Active"),
    ("inactive", "Inactive"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
    ("failed", "Failed"),
    ("archived", "Archived"),
    ("deleted", "Deleted"),
    ("suspended", "Suspended"),
    ("expired", "Expired"),
]


cloudinary.config(
    cloud_name=settings.CLOUD_NAME,
    api_key=settings.API_KEY,
    api_secret=settings.API_SECRET
)


# Create your models here.

class Category(models.Model):
    title = models.CharField(max_length=300)
    active = models.BooleanField(default=False)

    slug = models.SlugField(unique=True, null=True, blank=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title




class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, null=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)




class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)

    name = models.CharField(max_length=500)
    slug = models.SlugField(unique=True, null=True, blank=True)
    product_id = ShortUUIDField(unique=True, length=7, max_length=20)

    description = models.TextField(max_length=2000, null=True, blank=True)
    features = models.JSONField(null=True, blank=True, default=list)  # For LLM insight
    tags = models.ManyToManyField("Tag", blank=True, related_name="products")
    product_type = models.CharField(max_length=50, null=True, blank=True)  # e.g., "prompt pack", "course", etc.
    useCases = models.JSONField(null=True, blank=True, default=list)
    benefits = models.JSONField(null=True, blank=True, default=list)
    value = models.CharField(max_length=500,null=True,blank=True)
    # Links & media
    url = models.URLField(max_length=500, null=True, blank=True)
    image = CloudinaryField('image', null=True, blank=True)
    files = models.FileField(upload_to="products/files/", blank=True, null=True)
    media_assets = models.JSONField(default=list, blank=True, null=True)  # e.g. [{"type": "video", "url": "..."}]

    # Pricing
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=20.00)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Campaign tracking
    is_active = models.BooleanField(default=True)
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            unique_slug = base_slug
            counter = 1
            while Product.objects.filter(slug=unique_slug).exists():
                unique_slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)

class AdsCreatives(models.Model):
    name = models.CharField(max_length=255,null=True,blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE,null=True,blank=True)
    platform = models.CharField(max_length=50, null=True,blank=True)
    creative_type = models.CharField(max_length=50,null=True,blank=True)  # Image, Video, Carousel, etc.
    file_url = CloudinaryField('image', null=True, blank=True)  # Link to image or video
    file_hash = models.CharField(max_length=100, blank=True, null=True)
    ad_copy = models.TextField(blank=True, null=True)  # Optional text to show with creative
    headline = models.CharField(max_length=255, blank=True, null=True)
    cta = models.CharField(max_length=100, default="Buy Now")
    is_active = models.BooleanField(default=True)  # e.g. {"interests": ["AI tools"], "age_range": "18-35"}
    performance_metrics = models.JSONField(default=dict, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    creative_id = ShortUUIDField(unique=True, length=7, max_length=20)
    slug = models.SlugField(unique=True, null=True, blank=True)




    def __str__(self):
        return f"{self.creative_type} for {self.file_url}"



class Campaign(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="campaigns")
    platform = models.CharField(max_length=50)
    all_platform = models.CharField(max_length=50, null=True, blank=True)
    audience = models.JSONField(null=True, blank=True)
    # e.g. {
    #     "interests": ["AI Tools", "Entrepreneurship"],
    #     "behaviors": ["Online Shoppers"],
    #     "demographics": {
    #         "age_min": 25,
    #         "age_max": 45,
    #         "education_statuses": ["College grads"],
    #         "relationship_statuses": ["Married"]
    #     },
    #     "gender": "all"
    # }

    # 📣 Ad structure
    ad_type = models.CharField(max_length=50, null=True, blank=True)
    ad_type_subtypes = models.CharField(max_length=50, null=True, blank=True)

    objective = models.CharField(max_length=500,null=True, blank=True)
    headline = models.CharField(max_length=255, blank=True, null=True)
    cta = models.CharField(max_length=100, default="Learn More")
    ad_copy = models.TextField(blank=True, null=True)  # Optional text to show with creative

    # 📸 Assets
    creatives = models.ManyToManyField(AdsCreatives, blank=True, related_name="campaigns")
    campaign_files = models.JSONField(default=list, blank=True, null=True)
    # e.g. [{"type": "image", "url": "..."}, {"type": "video", "url": "..."}]

    # 💬 AI summary
    description = models.TextField(blank=True, null=True)  # AI-written overview of campaign
    product_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # ⏱️ Timing
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='paused')

    # 📊 Performance
    result_metrics = models.JSONField(default=dict, blank=True)
    revenue = models.FloatField(default=0.0)  # manually updated from Gumroad
    purchase_roas = models.FloatField(default=0.0)  # calculated field
    purchases = models.CharField(max_length=5000,null=True,blank=True)
    conversion_rate = models.FloatField(default=0.0)
    # e.g. {"clicks": 230, "conversions": 14, "cpc": 0.34, "roi": 2.5}

    # 🆔 ID & timestamps
    campaign_id = ShortUUIDField(unique=True, length=7, max_length=20)
    meta_campaign_id = models.CharField(max_length=50,null=True,blank=True)
    meta_creative_id = models.CharField(max_length=50,null=True,blank=True)
    meta_ad_id = models.CharField(max_length=50,null=True,blank=True)
    meta_adset_id = models.CharField(max_length=50,null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.product.name} - {self.platform} Campaign"


class CampaignSummary(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="campaign_summary")
    product = models.ForeignKey(Product,on_delete=models.CASCADE)
    audience = models.JSONField(default=dict, blank=True)
    ad_formats = models.JSONField(default=list, blank=True)
    campaign_general_summary = models.TextField(max_length=1000,blank=True, null=True)
    headline = models.CharField(max_length=255, blank=True, null=True)
    cta = models.CharField(max_length=255, blank=True, null=True)
    date = models.DateTimeField(default=timezone.now)


    def __str__(self):
        return f"{self.product.name} for {self.campaign}"




class AudienceSegment(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="audiences")
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=2000, null=True, blank=True)
    interests = models.JSONField(default=list, blank=True)  # e.g. ["fitness", "ebooks", "freelancing"]
    demographics = models.JSONField(default=dict, blank=True)  # e.g. {"age": "18-34", "gender": "male", "location": "US"}
    platform = models.CharField(max_length=100)  # Meta, TikTok, etc.
    lookalike_score = models.FloatField(default=0.0)  # Optional scoring metric

    def __str__(self):
        return f"{self.name} for {self.campaign}"





class OptimizationLog(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="optimization_logs")
    product = models.ForeignKey(Product,on_delete=models.SET_NULL,null=True,blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=100,null=True,blank=True)  # "Shuffle creatives", "Pause campaign", etc.
    reason = models.CharField(max_length=100,null=True,blank=True)
    creative_used = models.ManyToManyField(AdsCreatives, blank=True, related_name="optimization_logs")
    notes = models.TextField(blank=True, null=True)
    metrics_snapshot = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Optimization for {self.campaign} - {self.action}"




#BACKDOOR


class Lead(models.Model):
    username = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255,null=True,blank=True)
    phone = models.CharField(max_length=30, blank=True, null=True)
    address = models.CharField(max_length=30, blank=True, null=True)
    email = models.EmailField(unique=False, blank=True, null=True)  # <--- allow null & not unique
    niche = models.CharField(max_length=255, blank=True, null=True)
    source_url = models.URLField(blank=True, null=True)
    external_urls = models.TextField(blank=True, null=True)
    source_name = models.CharField(null=True,blank=True,max_length=50)

    # GPT-related fields
    bio = models.TextField(blank=True,null=True)
    business_description = models.TextField(blank=True, null=True)

    gpt_subject = models.CharField(max_length=255, blank=True, null=True)
    outreach_email = models.TextField(blank=True, null=True)

    # Outreach tracking
    status = models.CharField(
        max_length=50,
        choices=[
            ('new', 'New'),
            ('scraped', 'Scraped'),
            ('email_generated', 'Email Generated'),
            ('sent', 'Sent'),
            ('replied', 'Replied'),
            ('converted', 'Converted'),
            ('failed', 'Failed')
        ],
        default='new'
    )
    last_contacted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    email_sent = models.BooleanField(default=False)
    followup_sent = models.BooleanField(default=False)

    valid = models.BooleanField(default=False)

    opened = models.BooleanField(default=False)
    opened_at = models.CharField(max_length=255, blank=True, null=True)
    responded = models.BooleanField(default=False)
    email_provider_used = models.CharField(max_length=50,null=True,blank=True)
    # Optional debug/log field
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.username} - {self.email} ({self.status})"


class PromptLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    prompt = models.TextField(max_length=2000, null=True, blank=True)
    response = models.TextField(max_length=2000, null=True, blank=True)
    date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.response} - {self.date}"


class EmailWarmupLog(models.Model):
    date = models.DateField(auto_now_add=True)
    sender_email = models.EmailField()
    emails_sent = models.PositiveIntegerField(default=0)
    inboxed = models.PositiveIntegerField(default=0)
    spam = models.PositiveIntegerField(default=0)
    replies_received = models.PositiveIntegerField(default=0)
    inboxes_tested = models.TextField(help_text="Comma-separated: Gmail, Yahoo, etc.")
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.sender_email} - {self.date}"


class DomainHealthCheck(models.Model):
    domain = models.CharField(max_length=100)
    checked_at = models.DateTimeField(auto_now_add=True)

    spam_score = models.DecimalField(max_digits=4, decimal_places=2, help_text="Score from 0–10 (Mail-Tester)")
    is_blacklisted = models.BooleanField(default=False)

    spf_valid = models.BooleanField(default=False)
    dkim_valid = models.BooleanField(default=False)
    dmarc_valid = models.BooleanField(default=False)

    tool_used = models.CharField(max_length=100, help_text="e.g., Mail-Tester, MXToolbox, GMass")
    report_link = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.domain} - {self.checked_at.strftime('%Y-%m-%d %H:%M')}"

