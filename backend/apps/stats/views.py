from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chats.models import Chat, ManagerStatus, Message, Rating
from apps.users.permissions import IsROP

User = get_user_model()


def _org_chat_qs(user):
    """Базовый queryset чатов, ограниченный организацией пользователя."""
    if user.role == 'manager':
        return Chat.objects.filter(assigned_manager=user)
    org_name = user.organization_name
    if org_name:
        return Chat.objects.filter(site__owner__organization_name=org_name)
    return Chat.objects.filter(site__owner=user)


def _org_user_qs(user):
    """Queryset пользователей в пределах той же организации."""
    org_name = user.organization_name
    if org_name:
        return User.objects.filter(organization_name=org_name)
    return User.objects.filter(pk=user.pk)


def _parse_date_range(request):
    """Парсит date_from и date_to из query params."""
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    period = request.query_params.get('period')  # today, week, month

    now = timezone.now()
    if period == 'today':
        date_from = now.date()
        date_to = now.date()
    elif period == 'week':
        date_from = (now - timedelta(days=7)).date()
        date_to = now.date()
    elif period == 'month':
        date_from = (now - timedelta(days=30)).date()
        date_to = now.date()

    return date_from, date_to


def _filter_chats_by_date(qs, date_from, date_to):
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs


class OverviewStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        today = timezone.now().date()
        date_from, date_to = _parse_date_range(request)

        chats_qs = _org_chat_qs(user)

        # Фильтр по сайту
        site_id = request.query_params.get('site')
        if site_id:
            chats_qs = chats_qs.filter(site_id=site_id)

        # Фильтр по датам
        filtered_qs = _filter_chats_by_date(chats_qs, date_from, date_to)

        total_chats = filtered_qs.count()
        active_chats = filtered_qs.exclude(status=Chat.Status.CLOSED).count()
        new_today = chats_qs.filter(created_at__date=today).count()
        closed_total = filtered_qs.filter(status=Chat.Status.CLOSED).count()

        # Средняя оценка (только по своей организации)
        avg_rating = Rating.objects.filter(
            chat__in=_org_chat_qs(user)
        ).aggregate(avg=Avg('rating'))['avg']

        # Распределение по каналам
        by_channel = dict(
            filtered_qs.values_list('channel').annotate(count=Count('id')).values_list('channel', 'count')
        )

        # Распределение по статусам
        by_status = dict(
            filtered_qs.values_list('status').annotate(count=Count('id')).values_list('status', 'count')
        )

        return Response({
            'total_chats': total_chats,
            'active_chats': active_chats,
            'new_today': new_today,
            'closed_total': closed_total,
            'avg_rating': round(avg_rating, 2) if avg_rating else None,
            'by_channel': by_channel,
            'by_status': by_status,
        })


class ManagerStatsView(APIView):
    permission_classes = [IsAuthenticated, IsROP]

    def get(self, request):
        date_from, date_to = _parse_date_range(request)
        managers = _org_user_qs(request.user).filter(role__in=['manager', 'rop'], is_active=True)
        result = []

        for manager in managers:
            chats = _org_chat_qs(request.user).filter(assigned_manager=manager)
            chats = _filter_chats_by_date(chats, date_from, date_to)
            ratings = Rating.objects.filter(manager=manager, chat__in=_org_chat_qs(request.user))
            avg_rating = ratings.aggregate(avg=Avg('rating'))['avg']

            try:
                status_obj = manager.manager_status
                current_status = status_obj.status
            except ManagerStatus.DoesNotExist:
                current_status = 'offline'

            # Среднее время первого ответа (секунды)
            avg_response_seconds = None
            chat_ids = list(chats.values_list('id', flat=True))
            if chat_ids:
                messages = (
                    Message.objects
                    .filter(chat_id__in=chat_ids, sender_type__in=['client', 'manager'])
                    .order_by('chat_id', 'timestamp')
                    .values('chat_id', 'sender_type', 'timestamp')
                )
                # Группируем сообщения по чату
                chat_msgs: dict = {}
                for msg in messages:
                    chat_msgs.setdefault(msg['chat_id'], []).append(msg)

                response_times = []
                for msgs in chat_msgs.values():
                    first_client = next((m for m in msgs if m['sender_type'] == 'client'), None)
                    if not first_client:
                        continue
                    first_reply = next(
                        (m for m in msgs
                         if m['sender_type'] == 'manager'
                         and m['timestamp'] > first_client['timestamp']),
                        None
                    )
                    if first_reply:
                        delta = (first_reply['timestamp'] - first_client['timestamp']).total_seconds()
                        if 0 <= delta <= 86400:  # отфильтровываем выбросы > 24 ч
                            response_times.append(delta)

                if response_times:
                    avg_response_seconds = int(sum(response_times) / len(response_times))

            result.append({
                'id': manager.id,
                'name': manager.first_name,
                'email': manager.email,
                'role': manager.role,
                'status': current_status,
                'total_chats': chats.count(),
                'active_chats': chats.exclude(status=Chat.Status.CLOSED).count(),
                'closed_chats': chats.filter(status=Chat.Status.CLOSED).count(),
                'avg_rating': round(avg_rating, 2) if avg_rating else None,
                'ratings_count': ratings.count(),
                'avg_response_time': avg_response_seconds,
            })

        return Response(result)


class ChatsTimelineView(APIView):
    """
    GET /api/stats/timeline/?period=month&site=1
    Возвращает количество заявок по дням для графика.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        date_from, date_to = _parse_date_range(request)

        if not date_from:
            date_from = (timezone.now() - timedelta(days=30)).date()
        if not date_to:
            date_to = timezone.now().date()

        user = request.user
        qs = _org_chat_qs(user)

        site_id = request.query_params.get('site')
        if site_id:
            qs = qs.filter(site_id=site_id)

        qs = _filter_chats_by_date(qs, date_from, date_to)

        data = (
            qs.annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(count=Count('id'))
            .order_by('date')
        )

        return Response({
            'timeline': [
                {'date': item['date'].isoformat(), 'count': item['count']}
                for item in data
            ]
        })


class RatingsStatsView(APIView):
    """
    GET /api/stats/ratings/
    Возвращает распределение оценок для графика.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ratings_qs = Rating.objects.filter(chat__in=_org_chat_qs(request.user))

        distribution = dict(
            ratings_qs.values_list('rating')
            .annotate(count=Count('id'))
            .values_list('rating', 'count')
        )

        # Заполняем пустые значения
        result = {str(i): distribution.get(i, 0) for i in range(1, 6)}

        avg = ratings_qs.aggregate(avg=Avg('rating'))['avg']
        total = ratings_qs.count()

        return Response({
            'distribution': result,
            'avg_rating': round(avg, 2) if avg else None,
            'total_ratings': total,
        })
