# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
# Copyright (c) 2014 Mozilla Corporation
#

ROOT_DIR        := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))

AWS_REGION	:= us-west-2
## See also iam-cis-well-known-endpoint-prod
S3_BUCKET_NAME	:= iam-cis-well-known-endpoint-dev
S3_BUCKET_URI   := s3://$(S3_BUCKET_NAME)/
## Change to mozilla.com for prod - make sure there's no comments or spaces
## after this value (that's why this comment is above it and not inline)
DOMAIN		:= allizom.org
## Change to test. or empty string (prod) as needed (see also DOMAIN above)
STAGE		:= dev.
INFOSEC_FP	:= 85D77543B3D624B63CEA9E6DBC17301B491B3F21

.PHONY:all
all:
	@echo 'Available make targets:'
	@grep '^[^#[:space:]^\.PHONY.*].*:' Makefile

.PHONY: create-s3-bucket
create-s3-bucket:
	@export AWS_REGION=$(AWS_REGION)
	aws s3api create-bucket --bucket $(S3_BUCKET_NAME) --acl public-read --create-bucket-configuration LocationConstraint=$(AWS_REGION)

.PHONY: upload-s3-bucket
upload-s3-bucket: test verify
	@export AWS_REGION=$(AWS_REGION)
	aws s3 sync --content-type 'application/json' s3/ $(S3_BUCKET_URI) --acl public-read

.PHONY: templatize
templatize:
	@echo Templatizing...
	cp tpl/* s3/.well-known
	sed -i 's/$${DOMAIN}/$(DOMAIN)/g' s3/.well-known/*
	sed -i 's/$${STAGE}/$(STAGE)/g' s3/.well-known/*

.PHONY: cloudformation
cloudformation: cloudformation.yml

.PHONY: verify sign
verify:
	gpg --verify s3/.well-known/mozilla-iam.asc 2>&1 | grep "using RSA key" | grep $(INFOSEC_FP)

sign: templatize
	cd s3/.well-known && gpg --default-key $(INFOSEC_FP) -sab mozilla-iam
	cd s3/.well-known && gpg --default-key $(INFOSEC_FP) -sab mozilla-iam-publisher-rules

test: tests/test_format.py
	pytest tests
