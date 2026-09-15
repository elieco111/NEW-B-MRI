# B-MRI CoreFocus™ Platform

This is the complete custom platform for **B-MRI** that implements the complete **CoreFocus™** client workflow from discovery through dynamic live sessions to final execution blueprint generation.

## Features

1. **Backoffice Console**: Manage clients, view core maps, generate unique questionnaire links.
2. **CoreHeuristic™ Analytics Engine**: Scans text in incoming questionnaires and auto-extracts focus points (tactical or strategic) along with a confidence score.
3. **Live Presenter & Vote System**: Run real-time interactive slide sessions (using HTML5 WebSockets) where participants scan a QR code to vote and see live results directly.
4. **PDF Summary Generator**: Dynamic document creation conforming to professional formatting guidelines with custom ReportLab rules.

## Deployment on Railway

1. Upload this codebase to a private or public GitHub repository.
2. Link your repository to a new service card in Railway.
3. Create a domain or CNAME record mapping `app.b-mri.com` to your Railway service's address.
