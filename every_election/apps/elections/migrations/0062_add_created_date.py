# Generated by Django 2.2.20 on 2021-09-28 15:24

from django.db import migrations
from django.db.models import F, ExpressionWrapper, DateField
from django.utils.timezone import timedelta


def add_created_date(apps, schema_editor):
    Election = apps.get_model("elections", "Election")
    delta = timedelta(weeks=8)
    expression = ExpressionWrapper(F("poll_open_date") - delta, output_field=DateField)
    Election.private_objects.update(created=expression)


class Migration(migrations.Migration):

    dependencies = [
        ("elections", "0061_auto_20210928_1509"),
    ]

    operations = [
        migrations.RunPython(
            code=add_created_date, reverse_code=migrations.RunPython.noop
        )
    ]
