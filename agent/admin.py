from django.contrib import admin
from .models import *

# Register your models here.






class AdsCreativesAdmin(admin.ModelAdmin):
    list_display = ('name', 'file_hash','cta','is_active')





class CampaignAdmin(admin.ModelAdmin):
    list_display = ('product', 'platform','budget','start_date','meta_creative_id','end_date','status')






class HasEmailFilter(admin.SimpleListFilter):
    title = 'Has Email'
    parameter_name = 'has_email'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Has Email'),
            ('no', 'No Email'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'yes':
            return queryset.filter(email__isnull=False).exclude(email__exact='')
        elif value == 'no':
            return queryset.filter(email__isnull=True) | queryset.filter(email__exact='')
        return queryset


class LeadAdmin(admin.ModelAdmin):
    list_display = ('external_urls','bio', 'business_description', 'email', 'niche', 'source_url', 'status')
    list_filter = ('niche', 'status', HasEmailFilter)  # Use custom filter class here
    ordering = ('-email',)
    search_fields = ('username', 'email', 'business_description','niche')  # Add any other fields you want to make searchable





@admin.register(EmailWarmupLog)
class EmailWarmupLogAdmin(admin.ModelAdmin):
    list_display = (
        'date', 'sender_email', 'emails_sent', 'inboxed', 'spam', 'replies_received'
    )
    list_filter = ('date', 'sender_email')
    search_fields = ('sender_email', 'notes')
    readonly_fields = ('date',)
    fieldsets = (
        (None, {
            'fields': (
                'date',
                'sender_email',
                ('emails_sent', 'inboxed', 'spam', 'replies_received'),
                'inboxes_tested',
                'notes'
            )
        }),
    )


@admin.register(DomainHealthCheck)
class DomainHealthCheckAdmin(admin.ModelAdmin):
    list_display = (
        'checked_at', 'domain', 'spam_score', 'is_blacklisted',
        'spf_valid', 'dkim_valid', 'dmarc_valid'
    )
    list_filter = ('domain', 'checked_at', 'is_blacklisted')
    search_fields = ('domain', 'tool_used', 'notes')
    readonly_fields = ('checked_at',)
    fieldsets = (
        (None, {
            'fields': (
                'checked_at',
                'domain',
                ('spam_score', 'is_blacklisted'),
                ('spf_valid', 'dkim_valid', 'dmarc_valid'),
                'tool_used',
                'report_link',
                'notes',
            )
        }),
    )






admin.site.register(Product)
admin.site.register(Campaign,CampaignAdmin)
admin.site.register(AdsCreatives,AdsCreativesAdmin)
admin.site.register(AudienceSegment)
admin.site.register(OptimizationLog)
admin.site.register(PromptLog)
admin.site.register(Lead,LeadAdmin)

