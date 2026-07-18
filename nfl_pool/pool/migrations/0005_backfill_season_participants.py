from django.db import migrations


def backfill_participants(apps, schema_editor):
    Pick = apps.get_model('pool', 'Pick')
    SeasonParticipant = apps.get_model('pool', 'SeasonParticipant')

    pairs = Pick.objects.values_list('user_id', 'week__season_id').distinct()
    for user_id, season_id in pairs:
        SeasonParticipant.objects.get_or_create(user_id=user_id, season_id=season_id)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pool', '0004_season_participant'),
    ]

    operations = [
        migrations.RunPython(backfill_participants, noop_reverse),
    ]
