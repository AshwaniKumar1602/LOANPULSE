from app.extensions import db
from app.models.notification import Notification, NotificationType


def create_notification(
    user_id: int,
    title: str,
    message: str,
    notification_type: str = NotificationType.APPLICATION_STATUS,
    link: str = None,
) -> Notification:
    """Creates an in-app notification for a user."""
    notif = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        link=link,
        is_read=False,
    )
    db.session.add(notif)
    db.session.commit()
    return notif
