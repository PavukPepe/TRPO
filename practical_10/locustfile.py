import random

from locust import HttpUser, TaskSet, SequentialTaskSet, task, between
from faker import Faker

fake_ru = Faker("ru_RU")
fake_en = Faker("en_US")

MANAGER_USERS = [
    {"email": "manager1@mail.ru", "password": "12341234"},
    {"email": "manager2@mail.ru", "password": "12341234"},
    {"email": "manager3@mail.ru", "password": "12341234"},
]

TEST_SITE_UUID = "bcf07ff4-fe1c-4c71-a77f-d656fc27f1e3"

class ManagerTaskSet(TaskSet):

    headers: dict = {}
    chat_ids: list = []

    def on_start(self):
        creds = random.choice(MANAGER_USERS)
        with self.client.post(
            "/api/auth/login/",
            json=creds,
            name="[AUTH] login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self.headers = {"Authorization": f"Bearer {resp.json().get('access', '')}"}
                resp.success()
            else:
                resp.failure(f"Login failed [{resp.status_code}]")

    @task(5)
    def browse_chats(self):
        with self.client.get(
            "/api/chats/",
            headers=self.headers,
            name="[CHATS] list",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    self.chat_ids = [c["id"] for c in results[:10]]
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    @task(5)
    def browse_templates(self):
        self.client.get(
            "/api/chats/templates/",
            headers=self.headers,
            name="[TEMPLATES] list",
        )

    @task(1)
    def send_message(self):
        if not self.chat_ids:
            return
        self.client.post(
            f"/api/chats/{random.choice(self.chat_ids)}/messages/",
            json={"content": fake_ru.sentence()},
            headers=self.headers,
            name="[MESSAGES] send",
        )


class ClientWidgetSequentialTaskSet(SequentialTaskSet):

    chat_id = None

    def on_start(self):
        self.chat_id = None

    @task(5)
    def step_config(self):
        self.client.get(f"/api/widget/{TEST_SITE_UUID}/config/", name="[WIDGET] config")

    @task
    def step_create_chat(self):
        with self.client.post(
            f"/api/widget/{TEST_SITE_UUID}/chat/",
            json={
                "client_name": fake_ru.name(),
                "client_email": fake_en.email(),
                "first_message": fake_ru.sentence(),
            },
            name="[WIDGET] create chat",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                body = resp.json()
                self.chat_id = body.get("id") or body.get("chat_id")
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")
        self.chat_id = None


class ManagerUser(HttpUser):
    tasks = [ManagerTaskSet]
    wait_time = between(1, 3)
    weight = 3


class WidgetClientUser(HttpUser):
    tasks = [ClientWidgetSequentialTaskSet]
    wait_time = between(3, 8)
    weight = 5
