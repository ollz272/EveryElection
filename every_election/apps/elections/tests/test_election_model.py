from freezegun import freeze_time

from django.utils import timezone
from django.test import TestCase
from elections.models import (
    DEFAULT_STATUS,
    Election,
    ModerationHistory,
    ModerationStatuses,
)
from elections.tests.factories import ElectionFactory
from elections.utils import ElectionBuilder
from .base_tests import BaseElectionCreatorMixIn


class TestElectionModel(BaseElectionCreatorMixIn, TestCase):
    def setUp(self):
        super().setUp()
        Election.private_objects.all().delete()
        self.election_group = ElectionBuilder(
            "local", "2017-06-08"
        ).build_election_group()
        self.org_group = (
            ElectionBuilder("local", "2017-06-08")
            .with_organisation(self.org1)
            .build_organisation_group(self.election_group)
        )
        self.ballot = (
            ElectionBuilder("local", "2017-06-08")
            .with_organisation(self.org1)
            .with_division(self.org_div_1)
            .build_ballot(self.org_group)
        )
        self.testshire_org_group = (
            ElectionBuilder("local", "2017-06-08")
            .with_organisation(self.testshire_org)
            .build_organisation_group(self.election_group)
        )

        self.testshire_ballot = (
            ElectionBuilder("local", "2017-06-08")
            .with_organisation(self.testshire_org)
            .with_division(self.testshire_div)
            .build_ballot(self.testshire_org_group)
        )

    def test_recursive_save_group(self):
        # table should be empty before we start
        self.assertEqual(0, Election.private_objects.count())

        # saving the child record should implicitly save the parent record too
        self.org_group.save()
        self.assertEqual(2, Election.private_objects.count())

    def test_recursive_save_ballot(self):
        # table should be empty before we start
        self.assertEqual(0, Election.private_objects.count())

        # From a performance perspective, saving a ballot and 2 parent groups
        # is the worst-case scenario for database I/O
        # we should monitor this and be aware if this number increases
        with self.assertNumQueries(19):
            self.ballot.save()

        # saving the child record should implicitly save the parent records too
        self.assertEqual(3, Election.private_objects.count())

    def test_transaction_rollback_parent(self):
        # table should be empty before we start
        self.assertEqual(0, Election.private_objects.count())

        # doing this will cause save() to throw a exception
        # if we try to save parent_record
        self.election_group.organisation_id = "foo"

        try:
            self.org_group.save()
        except ValueError:
            pass

        # the exception should have prevented both the
        # parent and child records from being saved
        self.assertEqual(0, Election.private_objects.count())

    def test_transaction_rollback_child(self):
        # table should be empty before we start
        self.assertEqual(0, Election.private_objects.count())

        # doing this will cause save() to throw a exception
        # if we try to save child_record
        self.org_group.organisation_id = "foo"

        try:
            self.org_group.save()
        except ValueError:
            pass

        # the exception should have prevented both the
        # parent and child records from being saved
        self.assertEqual(0, Election.private_objects.count())

    def test_related_object_save(self):
        # table should be empty before we start
        self.assertEqual(0, ModerationHistory.objects.count())

        # the first time we save a record, we should create
        # a corresponding moderation status event
        self.election_group.save()
        self.assertEqual(1, ModerationHistory.objects.count())

        # saving the same record again shouldn't though
        self.election_group.seats_contests = 7
        self.election_group.source = "some bloke down the pub told me"
        self.election_group.save()
        self.assertEqual(1, ModerationHistory.objects.count())

    def test_save_with_status(self):
        self.election_group.save()
        self.assertEqual(
            self.election_group.moderation_status.short_label, DEFAULT_STATUS
        )

        self.election_group.save(status=ModerationStatuses.approved.value)
        self.assertEqual(
            self.election_group.moderation_status.short_label,
            ModerationStatuses.approved.value,
        )

    def test_get_ballots(self):
        for election in [
            self.election_group,
            self.testshire_org_group,
            self.testshire_ballot,
            self.org_group,
            self.ballot,
        ]:
            election.save(status=ModerationStatuses.approved.value)

        self.assertEqual(
            len(self.org_group.get_ballots()),
            1,
        )
        self.assertEqual(len(self.election_group.get_ballots()), 2)

    def test_group_seats_contested(self):

        for election in [
            self.election_group,
            self.testshire_org_group,
            self.org_group,
        ]:
            election.save(status=ModerationStatuses.approved.value)

        for ballot in [
            self.testshire_ballot,
            self.ballot,
        ]:
            ballot.seats_contested = 3
            ballot.save(status=ModerationStatuses.approved.value)

        self.assertEqual(self.ballot.group_seats_contested, 3)
        self.assertEqual(self.org_group.group_seats_contested, 3)
        self.assertEqual(self.election_group.group_seats_contested, 6)

    def test_get_admin_url(self):
        election = Election(pk=2021)
        self.assertEqual(
            election.get_admin_url(),
            f"/admin/elections/election/{election.pk}/change/",
        )


class TestModified(TestCase):
    def test_update_changes_modified(self):
        election = ElectionFactory()

        future = timezone.datetime(2022, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
        with freeze_time("2022-5-5 12:00:00"):
            self.assertNotEqual(election.modified, future)
            Election.private_objects.update()
            election.refresh_from_db()
            self.assertEqual(election.modified, future)
