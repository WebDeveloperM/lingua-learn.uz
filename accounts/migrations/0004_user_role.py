from django.db import migrations, models


def make_superusers_admins(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(is_superuser=True).update(role='admin')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_user_managers_remove_user_username_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('student', "O'quvchi")], default='student', max_length=10, verbose_name='Rol'),
        ),
        migrations.RunPython(make_superusers_admins, migrations.RunPython.noop),
    ]
