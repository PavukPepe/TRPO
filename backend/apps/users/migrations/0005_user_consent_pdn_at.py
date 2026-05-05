from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_user_plan'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='consent_pdn_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Согласие на обработку ПДн (ФЗ-152)',
            ),
        ),
    ]
