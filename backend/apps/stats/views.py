from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.utils.timezone import localdate
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chats.models import Chat, ManagerStatus, Message, Rating
from apps.sites.models import Site
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


def _org_site_qs(user):
    """Queryset сайтов в пределах той же организации."""
    org_name = user.organization_name
    if org_name:
        return Site.objects.filter(owner__organization_name=org_name)
    return Site.objects.filter(owner=user)


def _parse_iso_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _parse_date_range(request):
    """Парсит date_from и date_to из query params. Всегда возвращает date|None.

    Используем localdate() (текущая дата в TIME_ZONE='Europe/Moscow') —
    это совпадает с тем, как Django раскручивает created_at__date в фильтрах
    при USE_TZ=True, иначе UTC-дата сервера может расходиться с локальной
    датой записи на 1 сутки.
    """
    period = request.query_params.get('period')  # today, week, month
    today = localdate()

    if period == 'today':
        return today, today
    if period == 'week':
        return today - timedelta(days=7), today
    if period == 'month':
        return today - timedelta(days=30), today

    return (
        _parse_iso_date(request.query_params.get('date_from')),
        _parse_iso_date(request.query_params.get('date_to')),
    )


def _filter_chats_by_date(qs, date_from, date_to):
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs


def _filter_ratings_by_date(qs, date_from, date_to):
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs


def _calculate_avg_first_response(chat_ids):
    if not chat_ids:
        return None

    messages = (
        Message.objects
        .filter(chat_id__in=chat_ids, sender_type__in=['client', 'manager'])
        .order_by('chat_id', 'timestamp')
        .values('chat_id', 'sender_type', 'timestamp')
    )

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
            None,
        )
        if first_reply:
            delta = (first_reply['timestamp'] - first_client['timestamp']).total_seconds()
            if 0 <= delta <= 86400:
                response_times.append(delta)

    if response_times:
        return int(sum(response_times) / len(response_times))
    return None


class OverviewStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        today = localdate()
        date_from, date_to = _parse_date_range(request)

        chats_qs = _org_chat_qs(user)

        site_id = request.query_params.get('site')
        if site_id:
            chats_qs = chats_qs.filter(site_id=site_id)

        manager_id = request.query_params.get('manager')
        if manager_id:
            chats_qs = chats_qs.filter(assigned_manager_id=manager_id)

        filtered_qs = _filter_chats_by_date(chats_qs, date_from, date_to)

        total_chats = filtered_qs.count()
        active_chats = filtered_qs.exclude(status=Chat.Status.CLOSED).count()
        new_today = chats_qs.filter(created_at__date=today).count()
        closed_total = filtered_qs.filter(status=Chat.Status.CLOSED).count()

        ratings_qs = _filter_ratings_by_date(
            Rating.objects.filter(chat__in=filtered_qs), date_from, date_to,
        )
        avg_rating = ratings_qs.aggregate(avg=Avg('rating'))['avg']

        avg_response_seconds = _calculate_avg_first_response(
            list(filtered_qs.values_list('id', flat=True))
        )

        by_channel = dict(
            filtered_qs.values_list('channel').annotate(count=Count('id')).values_list('channel', 'count')
        )
        by_status = dict(
            filtered_qs.values_list('status').annotate(count=Count('id')).values_list('status', 'count')
        )

        return Response({
            'total_chats': total_chats,
            'active_chats': active_chats,
            'new_today': new_today,
            'closed_total': closed_total,
            'avg_rating': round(avg_rating, 2) if avg_rating else None,
            'avg_response_time': avg_response_seconds,
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
            ratings = _filter_ratings_by_date(
                Rating.objects.filter(manager=manager, chat__in=_org_chat_qs(request.user)),
                date_from, date_to,
            )
            avg_rating = ratings.aggregate(avg=Avg('rating'))['avg']

            try:
                current_status = manager.manager_status.status
            except ManagerStatus.DoesNotExist:
                current_status = 'offline'

            avg_response_seconds = _calculate_avg_first_response(
                list(chats.values_list('id', flat=True))
            )

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


class SiteStatsView(APIView):
    """
    GET /api/stats/sites/?period=month
    Статистика по сайтам организации: чаты, отклик, оценки, каналы.
    """
    permission_classes = [IsAuthenticated, IsROP]

    def get(self, request):
        date_from, date_to = _parse_date_range(request)
        sites = _org_site_qs(request.user)
        org_chats = _org_chat_qs(request.user)
        result = []

        for site in sites:
            chats = _filter_chats_by_date(org_chats.filter(site=site), date_from, date_to)
            chat_ids = list(chats.values_list('id', flat=True))

            ratings = _filter_ratings_by_date(
                Rating.objects.filter(chat_id__in=chat_ids), date_from, date_to,
            )
            avg_rating = ratings.aggregate(avg=Avg('rating'))['avg']

            avg_response_seconds = _calculate_avg_first_response(chat_ids)

            by_channel = dict(
                chats.values_list('channel').annotate(count=Count('id')).values_list('channel', 'count')
            )
            by_status = dict(
                chats.values_list('status').annotate(count=Count('id')).values_list('status', 'count')
            )

            result.append({
                'id': site.id,
                'name': site.name,
                'url': site.url,
                'total_chats': chats.count(),
                'active_chats': chats.exclude(status=Chat.Status.CLOSED).count(),
                'closed_chats': chats.filter(status=Chat.Status.CLOSED).count(),
                'avg_rating': round(avg_rating, 2) if avg_rating else None,
                'ratings_count': ratings.count(),
                'avg_response_time': avg_response_seconds,
                'by_channel': by_channel,
                'by_status': by_status,
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
            date_from = localdate() - timedelta(days=30)
        if not date_to:
            date_to = localdate()

        user = request.user
        qs = _org_chat_qs(user)

        site_id = request.query_params.get('site')
        if site_id:
            qs = qs.filter(site_id=site_id)

        manager_id = request.query_params.get('manager')
        if manager_id:
            qs = qs.filter(assigned_manager_id=manager_id)

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
        date_from, date_to = _parse_date_range(request)
        ratings_qs = _filter_ratings_by_date(
            Rating.objects.filter(chat__in=_org_chat_qs(request.user)),
            date_from, date_to,
        )

        distribution = dict(
            ratings_qs.values_list('rating')
            .annotate(count=Count('id'))
            .values_list('rating', 'count')
        )
        result = {str(i): distribution.get(i, 0) for i in range(1, 6)}

        avg = ratings_qs.aggregate(avg=Avg('rating'))['avg']
        total = ratings_qs.count()

        return Response({
            'distribution': result,
            'avg_rating': round(avg, 2) if avg else None,
            'total_ratings': total,
        })
