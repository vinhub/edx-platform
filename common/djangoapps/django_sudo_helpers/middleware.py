"""
Django sudo middleware.
"""
from django.conf import settings

import analytics
from eventtracking import tracker

from xmodule.modulestore.django import modulestore
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey


class DjangoSudoMiddleware(object):
    """
    Django sudo middleware to load course/library.
    """

    def process_request(self, request):
        """ Process the middleware request. """
        if 'region' in request.GET:
            load_course_or_library(request)

    def process_response(self, request, response):
        """Process the middleware response."""
        if request.path.startswith('/sudo/') and request.method == 'POST':
            if request.is_sudo(request.GET.get('region')):
                # Track user's login with sudo.
                if (hasattr(settings, 'LMS_SEGMENT_KEY') and settings.LMS_SEGMENT_KEY) \
                        or (hasattr(settings, 'CMS_SEGMENT_KEY') and settings.CMS_SEGMENT_KEY):
                    user = request.user
                    tracking_context = tracker.get_tracker().resolve_context()
                    analytics.identify(user.id, {
                        'email': user.email,
                        'username': user.username
                    })

                    analytics.track(
                        user.id,
                        "edx.bi.user.account.authenticated",
                        {
                            'category': "conversion",
                            'label': None,
                            'provider': None,
                            'is_sudo': True
                        },
                        context={
                            'ip': tracking_context.get('ip'),
                            'Google Analytics': {
                                'clientId': tracking_context.get('client_id')
                            }
                        }
                    )
        return response


def load_course_or_library(request):
    """
    Get course/library from region if not None and set on request object.
    """
    region = request.GET.get('region')
    if region:
        # parse out the course_id into a course_key
        try:
            course_key = CourseKey.from_string(region)
            if 'library' in region:
                request.library = modulestore().get_library(course_key)
            else:
                request.course = modulestore().get_course(course_key)
        except InvalidKeyError:
            pass
