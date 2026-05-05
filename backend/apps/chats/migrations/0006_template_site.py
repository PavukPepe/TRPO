import django.db.models.deletion
from django.db import migrations, models


def clear_templates(apps, schema_editor):
    """Удаляем существующие шаблоны: ранее они были привязаны к пользователю,
    после миграции — к сайту, миграция данных невозможна без догадок.
    """
    Template = apps.get_model('chats', 'Template')
    Template.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('chats', '0005_contact_consent_pdn_at'),
        ('sites', '0003_site_email_enabled_site_email_imap_host_and_more'),
    ]

    operations = [
        migrations.RunPython(clear_templates, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='template',
            name='user',
        ),
        migrations.AddField(
            model_name='template',
            name='site',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='templates',
                to='sites.site',
                verbose_name='Сайт',
            ),
        ),
    ]
