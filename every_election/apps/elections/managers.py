from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.gis.db.models.functions import PointOnSurface
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.contrib.gis.geos import Point, GEOSGeometry
from django.utils import timezone
from elections.query_helpers import get_point_from_postcode


class ElectionQuerySet(models.QuerySet):
    def for_point(self, point):
        return self.filter(
            models.Q(division_geography__geography__contains=point)
            | models.Q(organisation_geography__geography__contains=point)
        )

    def for_lat_lng(self, lat, lng):
        point = Point(lng, lat)
        return self.for_point(point)

    def for_postcode(self, postcode):
        point = get_point_from_postcode(postcode)
        return self.for_point(point)

    def ballots_with_point_in_area(self, area: GEOSGeometry):
        """
        Returns all election objects whose 'group_type' is 'None' and where the
        *centroid* of either the division or organisation (where there is no
        DivisionGeography) is inside the area
        """
        return (
            self.filter(group_type=None)
            .annotate(
                division_centroid=PointOnSurface("division_geography__geography"),
                organisation_centroid=PointOnSurface(
                    "organisation_geography__geography"
                ),
            )
            .filter(
                models.Q(division_centroid__within=area)
                | models.Q(organisation_centroid__within=area, division_centroid=None)
            )
        )

    def current(self):
        recent_past = datetime.today() - timedelta(days=settings.CURRENT_PAST_DAYS)
        near_future = datetime.today() + timedelta(days=settings.CURRENT_FUTURE_DAYS)
        return self.filter(
            (
                models.Q(poll_open_date__gte=recent_past)
                & models.Q(poll_open_date__lte=near_future)
            )
            | models.Q(current=True)
        ).exclude(current=False)

    def future(self):
        return self.filter(poll_open_date__gte=datetime.today())

    def filter_by_status(self, status):
        if isinstance(status, list):
            query = models.Q(moderationhistory__status__short_label__in=status)
        elif isinstance(status, str):
            query = models.Q(moderationhistory__status__short_label=status)
        else:
            raise TypeError("Expected list or str found {}".format(type(status)))

        return (
            self.annotate(latest_status=models.Max("moderationhistory__modified"))
            .filter(
                query & models.Q(moderationhistory__modified=models.F("latest_status"))
            )
            .order_by("election_id")
        )

    def update(self, update_modified=True, **kwargs):
        """
        By default updates the modified timestamp for objects in the QuerySet
        whenever update is called. Allows timestamp to be specified in the
        kwargs or defaults to current time.
        """
        if update_modified:
            kwargs["modified"] = kwargs.get("modified", timezone.now())
        return super().update(**kwargs)


class PublicElectionsManager(models.Manager.from_queryset(ElectionQuerySet)):

    """
    In most cases, we want to expose elections which are approved
    and hide any which are suggested/rejected/deleted
    Instead of remembering to filter on (latest status == approved)
    in every front-end query we can use this manager.
    """

    def get_queryset(self):
        return super().get_queryset().filter_by_status("Approved")


class PrivateElectionsManager(models.Manager.from_queryset(ElectionQuerySet)):

    """
    In some contexts
    (some API outputs, moderation queue code, /admin, unit tests, etc)
    we do also need to reference suggested/rejected/deleted elections.
    In these situations we can explicitly use this manager to
    query all election objects.
    """

    use_in_migrations = True
