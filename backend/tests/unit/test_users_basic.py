from django.contrib.auth import get_user_model


def test_create_user(db):
    User = get_user_model()
    u = User.objects.create_user(username=None, email="u1@example.com", password="p", first_name='F')
    assert u.pk is not None
    assert u.check_password("p")
