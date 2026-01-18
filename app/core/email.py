import httpx
from typing import Optional
from app.core.config import settings


class EmailService:
    """Email service using Mailgun."""

    def __init__(self):
        self.api_key = settings.MAILGUN_API_KEY
        self.domain = settings.MAILGUN_DOMAIN
        self.region = settings.MAILGUN_REGION
        self.from_name = settings.FROM_NAME
        self.from_email = settings.FROM_EMAIL

        # Set base URL based on region
        if self.region == "eu":
            self.base_url = f"https://api.eu.mailgun.net/v3/{self.domain}"
        else:
            self.base_url = f"https://api.mailgun.net/v3/{self.domain}"

    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: Optional[str] = None,
    ) -> bool:
        """Send an email using Mailgun."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/messages",
                    auth=("api", self.api_key),
                    data={
                        "from": f"{self.from_name} <{self.from_email}>",
                        "to": to,
                        "subject": subject,
                        "html": html,
                        "text": text or "",
                    },
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Email error: {e}")
            return False

    async def send_verification_code(self, to: str, name: str, code: str) -> bool:
        """Send 6-digit email verification code."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .code {{ font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #FF6B6B; text-align: center; padding: 20px; background: #f5f5f5; border-radius: 8px; margin: 20px 0; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Welcome to Flame! 🔥</h1>
                <p>Hi {name},</p>
                <p>Thanks for signing up! Use the code below to verify your email address:</p>
                <div class="code">{code}</div>
                <p>This code expires in <strong>15 minutes</strong>.</p>
                <div class="footer">
                    <p>If you didn't create this account, you can safely ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """

        return await self.send_email(
            to=to,
            subject=f"Your Flame verification code: {code}",
            html=html,
            text=f"Hi {name}, your verification code is: {code}. This code expires in 15 minutes.",
        )

    async def send_password_reset_token(self, to: str, name: str, token: str) -> bool:
        """Send password reset link with token."""
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .button {{ display: inline-block; padding: 14px 28px; background-color: #FF6B6B; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; }}
                .footer {{ margin-top: 30px; font-size: 12px; color: #666; }}
                .link {{ word-break: break-all; color: #FF6B6B; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Reset Your Password</h1>
                <p>Hi {name},</p>
                <p>We received a request to reset your password. Click the button below to set a new password:</p>
                <p style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" class="button">Reset Password</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p class="link">{reset_url}</p>
                <p>This link expires in <strong>1 hour</strong>.</p>
                <div class="footer">
                    <p>If you didn't request this, you can safely ignore this email. Your password won't be changed.</p>
                </div>
            </div>
        </body>
        </html>
        """

        return await self.send_email(
            to=to,
            subject="Reset your Flame password",
            html=html,
            text=f"Hi {name}, reset your password by visiting: {reset_url}. This link expires in 1 hour.",
        )

    async def send_new_match_email(self, to: str, name: str, match_name: str) -> bool:
        """Send notification about a new match."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .button {{ display: inline-block; padding: 12px 24px; background-color: #FF6B6B; color: white; text-decoration: none; border-radius: 8px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>You have a new match! 🔥</h1>
                <p>Hi {name},</p>
                <p>Great news! You and <strong>{match_name}</strong> liked each other.</p>
                <p>Start a conversation and see where it goes!</p>
                <p><a href="{settings.FRONTEND_URL}/matches" class="button">View Match</a></p>
            </div>
        </body>
        </html>
        """

        return await self.send_email(
            to=to,
            subject=f"You matched with {match_name}! 🔥",
            html=html,
            text=f"Hi {name}, you matched with {match_name}!",
        )


# Global email instance
email_service = EmailService()
