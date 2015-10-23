"""
Tests for student enrollment.
"""
import ddt
from datetime import datetime, timedelta
import httpretty
from mock import patch
import unittest

from django.conf import settings
from django.core.urlresolvers import reverse
from django.test.utils import override_settings
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory
from util.testing import UrlResetMixin
from embargo.test_utils import restrict_course
from student.tests.factories import UserFactory, CourseModeFactory
from student.models import CourseEnrollment, CourseEnrollmentAttribute
from course_modes.models import CourseMode
from openedx.core.lib.commerce import ECOMMERCE_DATE_FORMAT

TEST_API_URL = 'http://www-internal.example.com/api'
TEST_API_SIGNING_KEY = 'edx'
JSON = 'application/json'


@ddt.ddt
@unittest.skipUnless(settings.ROOT_URLCONF == 'lms.urls', 'Test only valid in lms')
class EnrollmentTest(UrlResetMixin, ModuleStoreTestCase):
    """
    Test student enrollment, especially with different course modes.
    """

    USERNAME = "Bob"
    EMAIL = "bob@example.com"
    PASSWORD = "edx"

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    def setUp(self):
        """ Create a course and user, then log in. """
        super(EnrollmentTest, self).setUp('embargo')
        self.course = CourseFactory.create()
        self.user = UserFactory.create(username=self.USERNAME, email=self.EMAIL, password=self.PASSWORD)
        self.client.login(username=self.USERNAME, password=self.PASSWORD)

        self.urls = [
            reverse('course_modes_choose', kwargs={'course_id': unicode(self.course.id)})
        ]

    @ddt.data(
        # Default (no course modes in the database)
        # Expect that we're redirected to the dashboard
        # and automatically enrolled as "honor"
        ([], '', 'honor'),

        # Audit / Verified / Honor
        # We should always go to the "choose your course" page.
        # We should also be enrolled as "honor" by default.
        (['honor', 'verified', 'audit'], 'course_modes_choose', 'honor'),

        # Professional ed
        # Expect that we're sent to the "choose your track" page
        # (which will, in turn, redirect us to a page where we can verify/pay)
        # We should NOT be auto-enrolled, because that would be giving
        # away an expensive course for free :)
        (['professional'], 'course_modes_choose', None),
        (['no-id-professional'], 'course_modes_choose', None),
    )
    @ddt.unpack
    def test_enroll(self, course_modes, next_url, enrollment_mode):
        # Create the course modes (if any) required for this test case
        for mode_slug in course_modes:
            CourseModeFactory.create(
                course_id=self.course.id,
                mode_slug=mode_slug,
                mode_display_name=mode_slug,
            )

        # Reverse the expected next URL, if one is provided
        # (otherwise, use an empty string, which the JavaScript client
        # interprets as a redirect to the dashboard)
        full_url = (
            reverse(next_url, kwargs={'course_id': unicode(self.course.id)})
            if next_url else next_url
        )

        # Enroll in the course and verify the URL we get sent to
        resp = self._change_enrollment('enroll')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, full_url)

        # If we're not expecting to be enrolled, verify that this is the case
        if enrollment_mode is None:
            self.assertFalse(CourseEnrollment.is_enrolled(self.user, self.course.id))

        # Otherwise, verify that we're enrolled with the expected course mode
        else:
            self.assertTrue(CourseEnrollment.is_enrolled(self.user, self.course.id))
            course_mode, is_active = CourseEnrollment.enrollment_mode_for_user(self.user, self.course.id)
            self.assertTrue(is_active)
            self.assertEqual(course_mode, enrollment_mode)

    def test_unenroll(self):
        # Enroll the student in the course
        CourseEnrollment.enroll(self.user, self.course.id, mode="honor")

        # Attempt to unenroll the student
        resp = self._change_enrollment('unenroll')
        self.assertEqual(resp.status_code, 200)

        # Expect that we're no longer enrolled
        self.assertFalse(CourseEnrollment.is_enrolled(self.user, self.course.id))

    @patch.dict(settings.FEATURES, {'ENABLE_MKTG_EMAIL_OPT_IN': True})
    @patch('openedx.core.djangoapps.user_api.preferences.api.update_email_opt_in')
    @ddt.data(
        ([], 'true'),
        ([], 'false'),
        ([], None),
        (['honor', 'verified'], 'true'),
        (['honor', 'verified'], 'false'),
        (['honor', 'verified'], None),
        (['professional'], 'true'),
        (['professional'], 'false'),
        (['professional'], None),
        (['no-id-professional'], 'true'),
        (['no-id-professional'], 'false'),
        (['no-id-professional'], None),
    )
    @ddt.unpack
    def test_enroll_with_email_opt_in(self, course_modes, email_opt_in, mock_update_email_opt_in):
        # Create the course modes (if any) required for this test case
        for mode_slug in course_modes:
            CourseModeFactory.create(
                course_id=self.course.id,
                mode_slug=mode_slug,
                mode_display_name=mode_slug,
            )

        # Enroll in the course
        self._change_enrollment('enroll', email_opt_in=email_opt_in)

        # Verify that the profile API has been called as expected
        if email_opt_in is not None:
            opt_in = email_opt_in == 'true'
            mock_update_email_opt_in.assert_called_once_with(self.user, self.course.org, opt_in)
        else:
            self.assertFalse(mock_update_email_opt_in.called)

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    def test_embargo_restrict(self):
        # When accessing the course from an embargoed country,
        # we should be blocked.
        with restrict_course(self.course.id) as redirect_url:
            response = self._change_enrollment('enroll')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, redirect_url)

        # Verify that we weren't enrolled
        is_enrolled = CourseEnrollment.is_enrolled(self.user, self.course.id)
        self.assertFalse(is_enrolled)

    @patch.dict(settings.FEATURES, {'EMBARGO': True})
    def test_embargo_allow(self):
        response = self._change_enrollment('enroll')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, '')

        # Verify that we were enrolled
        is_enrolled = CourseEnrollment.is_enrolled(self.user, self.course.id)
        self.assertTrue(is_enrolled)

    def test_user_not_authenticated(self):
        # Log out, so we're no longer authenticated
        self.client.logout()

        # Try to enroll, expecting a forbidden response
        resp = self._change_enrollment('enroll')
        self.assertEqual(resp.status_code, 403)

    def test_missing_course_id_param(self):
        resp = self.client.post(
            reverse('change_enrollment'),
            {'enrollment_action': 'enroll'}
        )
        self.assertEqual(resp.status_code, 400)

    def test_unenroll_not_enrolled_in_course(self):
        # Try unenroll without first enrolling in the course
        resp = self._change_enrollment('unenroll')
        self.assertEqual(resp.status_code, 400)

    def test_invalid_enrollment_action(self):
        resp = self._change_enrollment('not_an_action')
        self.assertEqual(resp.status_code, 400)

    def test_with_invalid_course_id(self):
        CourseEnrollment.enroll(self.user, self.course.id, mode="honor")
        resp = self._change_enrollment('unenroll', course_id="edx/")
        self.assertEqual(resp.status_code, 400)

    def _change_enrollment(self, action, course_id=None, email_opt_in=None):
        """Change the student's enrollment status in a course.

        Args:
            action (str): The action to perform (either "enroll" or "unenroll")

        Keyword Args:
            course_id (unicode): If provided, use this course ID.  Otherwise, use the
                course ID created in the setup for this test.
            email_opt_in (unicode): If provided, pass this value along as
                an additional GET parameter.

        Returns:
            Response

        """
        if course_id is None:
            course_id = unicode(self.course.id)

        params = {
            'enrollment_action': action,
            'course_id': course_id
        }

        if email_opt_in:
            params['email_opt_in'] = email_opt_in

        return self.client.post(reverse('change_enrollment'), params)

    def _create_enrollment(self):
        """ Generate a default course mode and enrollment. """
        CourseMode.objects.create(
            course_id=self.course.id,
            mode_slug='verified',
            mode_display_name='Verified',
        )

        return CourseEnrollment(
            mode=CourseMode.VERIFIED,
            course_id=self.course.id,
            user=self.user,
        )

    def test_refundable_can_refund(self):
        """ Assert that enrollment is refundable if can_refund is set."""
        enrollment = self._create_enrollment()
        enrollment.can_refund = True

        self.assertTrue(enrollment.refundable())

    def test_refundable_generated_cert(self):
        """ Assert that enrollment is not refundable if cert has been generated."""
        with patch('student.models.GeneratedCertificate') as generate_cert:
            instance = generate_cert.return_value
            instance.certificate_for_student.return_value = True
            enrollment = self._create_enrollment()

            self.assertFalse(enrollment.refundable())

    def test_refundable_after_refund_window(self):
        """ Assert that enrollment is not refundable if it is after the refund_window_end_date."""
        with patch('student.models.CourseEnrollment._refund_window_end_date') as window:
            window.return_value = datetime.now() - timedelta(days=1)
            enrollment = self._create_enrollment()

            self.assertFalse(enrollment.refundable())

    def test_refundable_before_refund_window(self):
        """ Assert that enrollment is refundable if it is before the refund_window_end_date."""
        with patch('student.models.CourseEnrollment._refund_window_end_date') as window:
            window.return_value = datetime.now() + timedelta(days=1)
            enrollment = self._create_enrollment()

            self.assertTrue(enrollment.refundable())

    def test_refundable_no_verified(self):
        """ Assert that enrollment is not refundable if there is no verified course mode for the course."""
        CourseMode(
            course_id=self.course.id,
            mode_slug='honor',
            mode_display_name='Honor',
        )

        enrollment = CourseEnrollment(
            mode=CourseMode.HONOR,
            course_id=self.course.id,
            user=self.user,
        )

        self.assertFalse(enrollment.refundable())

    @ddt.data(
        (timedelta(days=1), timedelta(days=2), timedelta(days=2), 14),
        (timedelta(days=2), timedelta(days=1), timedelta(days=2), 14),
        (timedelta(days=1), timedelta(days=2), timedelta(days=2), 1),
        (timedelta(days=2), timedelta(days=1), timedelta(days=2), 1),
    )
    @ddt.unpack
    @httpretty.activate
    @override_settings(ECOMMERCE_API_SIGNING_KEY=TEST_API_SIGNING_KEY, ECOMMERCE_API_URL=TEST_API_URL)
    def test_refund_window_end_date(self, order_date_delta, course_start_delta, expected_date_delta, days):
        """ Assert that the later refund date is and config window timedelta are used to calculate window end date."""
        now = datetime.now().replace(microsecond=0)
        order_date = now + order_date_delta
        course_start = now + course_start_delta
        expected_date = now + expected_date_delta
        window_days = timedelta(days=days)

        order_number = 'OSCR-1000'

        expected_content = '{{"date_placed": "{date}"}}'.format(date=order_date.strftime(ECOMMERCE_DATE_FORMAT))
        httpretty.register_uri(
            httpretty.GET,
            '{url}/orders/{order}/'.format(url=TEST_API_URL, order=order_number),
            status=200, body=expected_content,
            adding_headers={'Content-Type': JSON}
        )

        enrollment = CourseEnrollment.objects.create(
            mode=CourseMode.VERIFIED,
            course_id=self.course.id,
            user=self.user,
        )
        enrollment.course_overview.start = course_start

        enrollment.attributes.add(CourseEnrollmentAttribute(  # pylint: disable=no-member
            enrollment=enrollment,
            namespace='order',
            name='order_number',
            value=order_number
        ))

        with patch('student.models.EnrollmentRefundConfiguration.current') as config:
            instance = config.return_value
            instance.refund_window = window_days
            self.assertEqual(
                enrollment._refund_window_end_date(),  # pylint: disable=protected-access
                expected_date + window_days
            )

    def test_refund_window_end_date_no_attributes(self):
        """ Assert that the None is returned when no order number attribute is found."""
        enrollment = CourseEnrollment(
            mode=CourseMode.VERIFIED,
            course_id=self.course.id,
            user=self.user,
        )

        self.assertIsNone(enrollment._refund_window_end_date())  # pylint: disable=protected-access
