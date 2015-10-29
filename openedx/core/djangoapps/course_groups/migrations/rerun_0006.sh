#!/bin/bash
./manage.py lms migrate --settings=devstack course_groups 0005 --fake
./manage.py lms migrate --settings=devstack course_groups 0006
