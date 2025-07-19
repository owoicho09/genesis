from agent.models import Product, OptimizationLog
from agent.tools.optimization.scheduler import send_campaign_alert


def get_product_specific_logs(product_id: str):
    """
    Fetches past campaign optimization logs for a product as structured dicts.
    Useful for LangChain agents to analyze what ad strategies worked or failed.
    Each log includes platform, audience, creatives, metrics, and actions taken.
    """
    logs = OptimizationLog.objects.filter(product_id=product_id)\
        .select_related("campaign", "product")\
        .prefetch_related("creative_used")\
        .order_by("-timestamp")

    formatted_logs = []

    for log in logs:
        campaign = log.campaign
        creative = log.campaign.creatives.first()
        formatted_logs.append({
            "product_name": campaign.product.name,
            "platform": campaign.platform,
            "ad_type": campaign.ad_type,
            "audience": campaign.audience,
            "objective": campaign.objective,
            "budget": float(campaign.budget),
            "creative_meta": {
                "headline": campaign.headline,
                "ad_copy": campaign.ad_copy,
                "type": getattr(creative, "creative_type", None),
                "hash": getattr(creative, "file_hash", None),
            } if creative else None,
            "start_metrics": log.metrics_snapshot,
            "action_taken": log.action,
            "reason": log.reason,
            "resulting_metrics": campaign.result_metrics,
            "roas": campaign.purchase_roas,
            "conversion_rate": campaign.conversion_rate,
            "final_outcome": campaign.status,
            "timestamp": log.timestamp.isoformat()
        })
        send_campaign_alert(campaign.product.name, campaign.ad_type)

    return formatted_logs
