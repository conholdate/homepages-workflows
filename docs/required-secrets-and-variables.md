# Required Secrets And Variables

This public repository must never contain secret values in files, logs, issues,
or pull requests. Add values only through GitHub Actions encrypted secrets.

## Required Secret Names

Source checkout:

- `HOMEPAGES_SOURCE_PAT`

S3-style deploy credentials:

- `ACCESS_KEY_SL`
- `SECRET_ACCESS_SL`
- `ACCESS_KEY`
- `SECRET_ACCESS`
- `HOMEPAGES_ACCESS_KEY`
- `HOMEPAGES_SECRET_ACCESS`

Ceph deploy credentials:

- `CEPH_QA_ACCESS_KEY_ID`
- `CEPH_QA_SECRET_ACCESS_KEY`
- `CEPH_PRODUCTION_ACCESS_KEY_ID`
- `CEPH_PRODUCTION_SECRET_ACCESS_KEY`

CDN purge:

- `BUNNY_API_KEY`

## Repository Variables

CloudFront distribution IDs are not secret, but they are kept as variables so
workflow code does not need to change when IDs rotate.

- `ASPOSE_COM_QA_CLOUDFRONT_DISTRIBUTION_ID`
- `ASPOSE_COM_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`
- `ASPOSE_CLOUD_QA_CLOUDFRONT_DISTRIBUTION_ID`
- `ASPOSE_CLOUD_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`
- `ASPOSE_APP_QA_CLOUDFRONT_DISTRIBUTION_ID`
- `ASPOSE_APP_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`
- `ASPOSE_AI_QA_CLOUDFRONT_DISTRIBUTION_ID`
- `ASPOSE_AI_PRODUCTION_CLOUDFRONT_DISTRIBUTION_ID`

## Current Scope

The generic deploy workflow maps:

- Aspose: `aspose.com`, `aspose.cloud`, `aspose.app`, `aspose.ai`,
  `aspose.net`, `aspose.org`
- GroupDocs: `groupdocs.com`, `groupdocs.cloud`, `groupdocs.app`
- Conholdate: `conholdate.com`, `conholdate.cloud`, `conholdate.app`

Koinize, CodePorting, Containerize, and other non-homepage targets should be
added only after the Aspose/GroupDocs/Conholdate migration is stable.
