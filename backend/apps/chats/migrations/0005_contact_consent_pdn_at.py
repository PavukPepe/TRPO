from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chats', '0004_chat_email_message_id_chat_email_subject_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='contact',
            name='consent_pdn_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Согласие на обработку ПДн (ФЗ-152)',
            ),
        ),
    ]
