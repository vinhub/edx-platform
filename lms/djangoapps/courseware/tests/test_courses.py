# -*- coding: utf-8 -*-
"""
Tests for course access
"""
from datetime import datetime, timedelta
import ddt
import itertools
import freezegun
import mock
import pytz
from nose.plugins.attrib import attr

from django.conf import settings
from django.test.utils import override_settings
from django.core.urlresolvers import reverse
from django.test.client import RequestFactory
from opaque_keys.edx.locations import SlashSeparatedCourseKey

from courseware.courses import (
    get_course_by_id, get_cms_course_link, course_image_url,
    get_course_info_section, get_course_about_section, get_cms_block_link
)

from course_modes.tests.factories import CourseModeFactory
from course_modes.models import CourseMode
from courseware.courses import get_course_with_access, _get_course_date_summary_blocks
from courseware.date_summary import (
    CourseEndDate,
    CourseStartDate,
    DateSummary,
    TodaysDate,
    VerificationDeadlineDate,
    VerifiedUpgradeDeadlineDate,
)
from courseware.module_render import get_module_for_descriptor
from courseware.tests.helpers import get_request_for_user
from courseware.model_data import FieldDataCache
from lms.djangoapps.courseware.courseware_access_exception import CoursewareAccessException
from openedx.core.djangoapps.self_paced.models import SelfPacedConfiguration
from student.tests.factories import CourseEnrollmentFactory, UserFactory
from verify_student.models import VerificationDeadline
from verify_student.tests.factories import SoftwareSecurePhotoVerificationFactory
from xmodule.modulestore.django import _get_modulestore_branch_setting, modulestore
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.xml_importer import import_course_from_xml
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase, SharedModuleStoreTestCase
from xmodule.modulestore.tests.django_utils import TEST_DATA_MIXED_TOY_MODULESTORE
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.tests.xml import factories as xml
from xmodule.tests.xml import XModuleXmlImportTest


CMS_BASE_TEST = 'testcms'
TEST_DATA_DIR = settings.COMMON_TEST_DATA_ROOT


@attr('shard_1')
class CoursesTest(ModuleStoreTestCase):
    """Test methods related to fetching courses."""

    @override_settings(CMS_BASE=CMS_BASE_TEST)
    def test_get_cms_course_block_link(self):
        """
        Tests that get_cms_course_link_by_id and get_cms_block_link_by_id return the right thing
        """
        self.course = CourseFactory.create(
            org='org', number='num', display_name='name'
        )

        cms_url = u"//{}/course/{}".format(CMS_BASE_TEST, unicode(self.course.id))
        self.assertEqual(cms_url, get_cms_course_link(self.course))
        cms_url = u"//{}/course/{}".format(CMS_BASE_TEST, unicode(self.course.location))
        self.assertEqual(cms_url, get_cms_block_link(self.course, 'course'))

    def test_get_course_with_access(self):
        user = UserFactory.create()
        course = CourseFactory.create(visible_to_staff_only=True)

        with self.assertRaises(CoursewareAccessException) as error:
            get_course_with_access(user, 'load', course.id)
        self.assertEqual(error.exception.message, "Course not found.")
        self.assertEqual(error.exception.access_response.error_code, "not_visible_to_user")
        self.assertFalse(error.exception.access_response.has_access)


@attr('shard_1')
class ModuleStoreBranchSettingTest(ModuleStoreTestCase):
    """Test methods related to the modulestore branch setting."""
    @mock.patch(
        'xmodule.modulestore.django.get_current_request_hostname',
        mock.Mock(return_value='preview.localhost')
    )
    @override_settings(
        HOSTNAME_MODULESTORE_DEFAULT_MAPPINGS={r'preview\.': ModuleStoreEnum.Branch.draft_preferred},
        MODULESTORE_BRANCH='fake_default_branch',
    )
    def test_default_modulestore_preview_mapping(self):
        self.assertEqual(_get_modulestore_branch_setting(), ModuleStoreEnum.Branch.draft_preferred)

    @mock.patch(
        'xmodule.modulestore.django.get_current_request_hostname',
        mock.Mock(return_value='localhost')
    )
    @override_settings(
        HOSTNAME_MODULESTORE_DEFAULT_MAPPINGS={r'preview\.': ModuleStoreEnum.Branch.draft_preferred},
        MODULESTORE_BRANCH='fake_default_branch',
    )
    def test_default_modulestore_branch_mapping(self):
        self.assertEqual(_get_modulestore_branch_setting(), 'fake_default_branch')


@attr('shard_1')
@override_settings(CMS_BASE=CMS_BASE_TEST)
class MongoCourseImageTestCase(ModuleStoreTestCase):
    """Tests for course image URLs when using a mongo modulestore."""

    def test_get_image_url(self):
        """Test image URL formatting."""
        course = CourseFactory.create(org='edX', course='999')
        self.assertEquals(course_image_url(course), '/c4x/edX/999/asset/{0}'.format(course.course_image))

    def test_non_ascii_image_name(self):
        # Verify that non-ascii image names are cleaned
        course = CourseFactory.create(course_image=u'before_\N{SNOWMAN}_after.jpg')
        self.assertEquals(
            course_image_url(course),
            '/c4x/{org}/{course}/asset/before___after.jpg'.format(
                org=course.location.org,
                course=course.location.course
            )
        )

    def test_spaces_in_image_name(self):
        # Verify that image names with spaces in them are cleaned
        course = CourseFactory.create(course_image=u'before after.jpg')
        self.assertEquals(
            course_image_url(course),
            '/c4x/{org}/{course}/asset/before_after.jpg'.format(
                org=course.location.org,
                course=course.location.course
            )
        )

    def test_static_asset_path_course_image_default(self):
        """
        Test that without course_image being set, but static_asset_path
        being set that we get the right course_image url.
        """
        course = CourseFactory.create(static_asset_path="foo")
        self.assertEquals(
            course_image_url(course),
            '/static/foo/images/course_image.jpg'
        )

    def test_static_asset_path_course_image_set(self):
        """
        Test that with course_image and static_asset_path both
        being set, that we get the right course_image url.
        """
        course = CourseFactory.create(course_image=u'things_stuff.jpg',
                                      static_asset_path="foo")
        self.assertEquals(
            course_image_url(course),
            '/static/foo/things_stuff.jpg'
        )


@attr('shard_1')
class XmlCourseImageTestCase(XModuleXmlImportTest):
    """Tests for course image URLs when using an xml modulestore."""

    def test_get_image_url(self):
        """Test image URL formatting."""
        course = self.process_xml(xml.CourseFactory.build())
        self.assertEquals(course_image_url(course), '/static/xml_test_course/images/course_image.jpg')

    def test_non_ascii_image_name(self):
        course = self.process_xml(xml.CourseFactory.build(course_image=u'before_\N{SNOWMAN}_after.jpg'))
        self.assertEquals(course_image_url(course), u'/static/xml_test_course/before_\N{SNOWMAN}_after.jpg')

    def test_spaces_in_image_name(self):
        course = self.process_xml(xml.CourseFactory.build(course_image=u'before after.jpg'))
        self.assertEquals(course_image_url(course), u'/static/xml_test_course/before after.jpg')


@attr('shard_1')
class CoursesRenderTest(ModuleStoreTestCase):
    """Test methods related to rendering courses content."""

    # TODO: this test relies on the specific setup of the toy course.
    # It should be rewritten to build the course it needs and then test that.
    def setUp(self):
        """
        Set up the course and user context
        """
        super(CoursesRenderTest, self).setUp()

        store = modulestore()
        course_items = import_course_from_xml(store, self.user.id, TEST_DATA_DIR, ['toy'])
        course_key = course_items[0].id
        self.course = get_course_by_id(course_key)
        self.request = get_request_for_user(UserFactory.create())

    def test_get_course_info_section_render(self):
        # Test render works okay
        course_info = get_course_info_section(self.request, self.course, 'handouts')
        self.assertEqual(course_info, u"<a href='/c4x/edX/toy/asset/handouts_sample_handout.txt'>Sample</a>")

        # Test when render raises an exception
        with mock.patch('courseware.courses.get_module') as mock_module_render:
            mock_module_render.return_value = mock.MagicMock(
                render=mock.Mock(side_effect=Exception('Render failed!'))
            )
            course_info = get_course_info_section(self.request, self.course, 'handouts')
            self.assertIn("this module is temporarily unavailable", course_info)

    @mock.patch('courseware.courses.get_request_for_thread')
    def test_get_course_about_section_render(self, mock_get_request):
        mock_get_request.return_value = self.request

        # Test render works okay
        course_about = get_course_about_section(self.course, 'short_description')
        self.assertEqual(course_about, "A course about toys.")

        # Test when render raises an exception
        with mock.patch('courseware.courses.get_module') as mock_module_render:
            mock_module_render.return_value = mock.MagicMock(
                render=mock.Mock(side_effect=Exception('Render failed!'))
            )
            course_about = get_course_about_section(self.course, 'short_description')
            self.assertIn("this module is temporarily unavailable", course_about)


@attr('shard_1')
class CourseDateSummaryTest(SharedModuleStoreTestCase):
    """Tests for course date summary blocks."""

    def setUp(self):
        SelfPacedConfiguration(enable_course_home_improvements=True).save()
        super(CourseDateSummaryTest, self).setUp()

    def setup_course_and_user(
            self,
            days_till_start=1,
            days_till_end=14,
            days_till_upgrade_deadline=4,
            enrollment_mode=CourseMode.VERIFIED,
            days_till_verification_deadline=14,
            verification_status=None,
    ):
        """Set up the course and user for this test."""
        now = datetime.now(pytz.UTC)
        self.course = CourseFactory.create(  # pylint: disable=attribute-defined-outside-init
            start=now + timedelta(days=days_till_start),
            end=now + timedelta(days=days_till_end),
        )
        self.user = UserFactory.create()  # pylint: disable=attribute-defined-outside-init

        if enrollment_mode is not None and days_till_upgrade_deadline is not None:
            CourseModeFactory.create(
                course_id=self.course.id,
                mode_slug=enrollment_mode,
                expiration_datetime=now + timedelta(days=days_till_upgrade_deadline)
            )
            CourseEnrollmentFactory.create(course_id=self.course.id, user=self.user, mode=enrollment_mode)
        else:
            CourseEnrollmentFactory.create(course_id=self.course.id, user=self.user)

        if days_till_verification_deadline is not None:
            VerificationDeadline.objects.create(
                course_key=self.course.id,
                deadline=now + timedelta(days=days_till_verification_deadline)
            )

        if verification_status is not None:
            SoftwareSecurePhotoVerificationFactory.create(user=self.user, status=verification_status)

    def test_course_info_feature_flag(self):
        SelfPacedConfiguration(enable_course_home_improvements=False).save()
        self.setup_course_and_user()
        url = reverse('info', args=(self.course.id,))
        response = self.client.get(url)
        self.assertNotIn('date-summary', response.content)

    # Tests for which blocks are enabled

    def assert_block_types(self, *expected_blocks):
        """Assert that the enabled block types for this course are as expected."""
        blocks = _get_course_date_summary_blocks(self.course, self.user)
        self.assertEqual(len(blocks), len(expected_blocks))
        self.assertEqual(set(type(b) for b in blocks), set(expected_blocks))

    def test_before_course_run(self):
        self.setup_course_and_user()
        self.assert_block_types(
            CourseEndDate,
            CourseStartDate,
            TodaysDate,
            VerificationDeadlineDate,
            VerifiedUpgradeDeadlineDate,
        )

    def test_after_course_run(self):
        self.setup_course_and_user(
            days_till_start=-10,
            days_till_end=-5,
            days_till_upgrade_deadline=-6,
            days_till_verification_deadline=-5,
            verification_status='approved'
        )
        self.assert_block_types(TodaysDate, CourseEndDate)

    def test_during_course_run(self):
        self.setup_course_and_user(
            days_till_start=-1,
        )
        self.assert_block_types(
            TodaysDate,
            CourseEndDate,
            VerificationDeadlineDate,
            VerifiedUpgradeDeadlineDate
        )

    def test_verification_approved(self):
        self.setup_course_and_user(
            days_till_start=-10,
            days_till_upgrade_deadline=-1,
            days_till_verification_deadline=1,
            verification_status='approved',
        )
        self.assert_block_types(TodaysDate, CourseEndDate)

    def test_after_upgrade_deadline(self):
        self.setup_course_and_user(
            days_till_start=-10,
            days_till_upgrade_deadline=-1,
        )
        self.assert_block_types(
            TodaysDate,
            CourseEndDate,
            VerificationDeadlineDate,
        )

    def test_after_verification_deadline(self):
        self.setup_course_and_user(
            days_till_start=-10,
            days_till_upgrade_deadline=-2,
            days_till_verification_deadline=-1,
        )
        self.assert_block_types(TodaysDate, CourseEndDate, VerificationDeadlineDate)

    # Specific block type tests

    ## Base DateSummary -- test empty defaults

    def test_date_summary(self):
        self.setup_course_and_user()
        block = DateSummary(self.course, self.user)
        html = '<div class="date-summary-container"><div class="date-summary date-summary-"></div></div>'
        self.assertHTMLEqual(block.render(), html)
        self.assertFalse(block.is_enabled)

    @freezegun.freeze_time('2015-01-02')
    def test_date_render(self):
        self.setup_course_and_user()
        block = DateSummary(self.course, self.user)
        block.date = datetime.now(pytz.UTC)
        self.assertIn('Jan 02, 2015', block.render())

    ## TodaysDate

    @freezegun.freeze_time('2015-01-02')
    def test_todays_date(self):
        self.setup_course_and_user()
        block = TodaysDate(self.course, self.user)
        self.assertTrue(block.is_enabled)
        self.assertEqual(block.date, datetime.now(pytz.UTC))
        self.assertEqual(block.title, 'Today is Jan 02, 2015')
        self.assertNotIn('date-summary-date', block.render())

    ## CourseStartDate

    def test_course_start_date(self):
        self.setup_course_and_user()
        block = CourseStartDate(self.course, self.user)
        self.assertEqual(block.date, self.course.start)

    ## CourseEndDate

    def test_course_end_date_during_course(self):
        self.setup_course_and_user(days_till_start=-1)
        block = CourseEndDate(self.course, self.user)
        self.assertEqual(
            block.description,
            'To earn a certificate, you must complete all requirements before this date.'
        )

    def test_course_end_date_after_course(self):
        self.setup_course_and_user(days_till_start=-2, days_till_end=-1)
        block = CourseEndDate(self.course, self.user)
        self.assertEqual(
            block.description,
            'This course is archived, which means you can review course content but it is no longer active.'
        )

    ## VerifiedUpgradeDeadlineDate

    @freezegun.freeze_time('2015-01-02')
    def test_verified_upgrade_deadline_date(self):
        self.setup_course_and_user(days_till_upgrade_deadline=1)
        block = VerifiedUpgradeDeadlineDate(self.course, self.user)
        self.assertEqual(block.date, datetime.now(pytz.UTC) + timedelta(days=1))
        self.assertEqual(block.link, reverse('verify_student_upgrade_and_verify', args=(self.course.id,)))

    def test_without_upgrade_deadline(self):
        self.setup_course_and_user(enrollment_mode=None)
        block = VerifiedUpgradeDeadlineDate(self.course, self.user)
        self.assertIsNone(block.date)

    ## VerificationDeadlineDate

    def test_no_verification_deadline(self):
        self.setup_course_and_user(days_till_start=-1, days_till_verification_deadline=None)
        block = VerificationDeadlineDate(self.course, self.user)
        self.assertFalse(block.is_enabled)

    def test_audit_mode(self):
        self.setup_course_and_user(days_till_start=-1, enrollment_mode=CourseMode.AUDIT)
        block = VerificationDeadlineDate(self.course, self.user)
        self.assertFalse(block.is_enabled)

    @freezegun.freeze_time('2015-01-02')
    def test_verification_deadline_date_upcoming(self):
        self.setup_course_and_user(days_till_start=-1)
        block = VerificationDeadlineDate(self.course, self.user)
        self.assertEqual(block.state, 'verification-deadline-upcoming')
        self.assertEqual(block.title, 'Verification Deadline')
        self.assertEqual(block.date, datetime.now(pytz.UTC) + timedelta(days=14))
        self.assertEqual(
            block.description,
            'You must successfully complete verification before this date to qualify for a Verified Certificate.'
        )
        self.assertEqual(block.link_text, 'Verify My Identity')
        self.assertEqual(block.link, reverse('verify_student_verify_now', args=(self.course.id,)))

    @freezegun.freeze_time('2015-01-02')
    def test_verification_deadline_date_retry(self):
        self.setup_course_and_user(days_till_start=-1, verification_status='denied')
        block = VerificationDeadlineDate(self.course, self.user)
        self.assertEqual(block.state, 'verification-deadline-retry')
        self.assertEqual(block.title, 'Verification Deadline')
        self.assertEqual(block.date, datetime.now(pytz.UTC) + timedelta(days=14))
        self.assertEqual(
            block.description,
            'You must successfully complete verification before this date to qualify for a Verified Certificate.'
        )
        self.assertEqual(block.link_text, 'Retry Verification')
        self.assertEqual(block.link, reverse('verify_student_reverify'))

    @freezegun.freeze_time('2015-01-02')
    def test_verification_deadline_date_denied(self):
        self.setup_course_and_user(
            days_till_start=-10,
            verification_status='denied',
            days_till_verification_deadline=-1,
        )
        block = VerificationDeadlineDate(self.course, self.user)
        self.assertEqual(block.state, 'verification-deadline-passed')
        self.assertEqual(block.title, 'Missed Verification Deadline')
        self.assertEqual(block.date, datetime.now(pytz.UTC) + timedelta(days=-1))
        self.assertEqual(
            block.description,
            "Unfortunately you missed this course's deadline for a successful verification."
        )
        self.assertEqual(block.link_text, 'Learn More')
        self.assertEqual(block.link, '')


@attr('shard_1')
class XmlCoursesRenderTest(ModuleStoreTestCase):
    """Test methods related to rendering courses content for an XML course."""
    MODULESTORE = TEST_DATA_MIXED_TOY_MODULESTORE

    toy_course_key = SlashSeparatedCourseKey('edX', 'toy', '2012_Fall')

    def test_get_course_info_section_render(self):
        course = get_course_by_id(self.toy_course_key)
        request = get_request_for_user(UserFactory.create())

        # Test render works okay. Note the href is different in XML courses.
        course_info = get_course_info_section(request, course, 'handouts')
        self.assertEqual(course_info, "<a href='/static/toy/handouts/sample_handout.txt'>Sample</a>")

        # Test when render raises an exception
        with mock.patch('courseware.courses.get_module') as mock_module_render:
            mock_module_render.return_value = mock.MagicMock(
                render=mock.Mock(side_effect=Exception('Render failed!'))
            )
            course_info = get_course_info_section(request, course, 'handouts')
            self.assertIn("this module is temporarily unavailable", course_info)


@attr('shard_1')
@ddt.ddt
class CourseInstantiationTests(ModuleStoreTestCase):
    """
    Tests around instantiating a course multiple times in the same request.
    """
    def setUp(self):
        super(CourseInstantiationTests, self).setUp()

        self.factory = RequestFactory()

    @ddt.data(*itertools.product(xrange(5), [ModuleStoreEnum.Type.mongo, ModuleStoreEnum.Type.split], [None, 0, 5]))
    @ddt.unpack
    def test_repeated_course_module_instantiation(self, loops, default_store, course_depth):

        with modulestore().default_store(default_store):
            course = CourseFactory.create()
            chapter = ItemFactory(parent=course, category='chapter', graded=True)
            section = ItemFactory(parent=chapter, category='sequential')
            __ = ItemFactory(parent=section, category='problem')

        fake_request = self.factory.get(
            reverse('progress', kwargs={'course_id': unicode(course.id)})
        )

        course = modulestore().get_course(course.id, depth=course_depth)

        for _ in xrange(loops):
            field_data_cache = FieldDataCache.cache_for_descriptor_descendents(
                course.id, self.user, course, depth=course_depth
            )
            course_module = get_module_for_descriptor(
                self.user,
                fake_request,
                course,
                field_data_cache,
                course.id,
                course=course
            )
            for chapter in course_module.get_children():
                for section in chapter.get_children():
                    for item in section.get_children():
                        self.assertTrue(item.graded)
