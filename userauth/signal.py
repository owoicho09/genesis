from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from userauth.models import User,Profile



@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        print('__________signal')
        Profile.objects.create(user=instance)



