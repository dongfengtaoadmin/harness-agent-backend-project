"""用户个人信息服务：处理UserProfile表的CRUD操作。"""

from typing import Optional
from sqlalchemy.orm import Session

from app.db.models import UserProfile


class UserProfileService:
    """用户个人信息服务。"""
    
    @staticmethod
    def get_user_profile(db: Session, user_id: int) -> Optional[UserProfile]:
        """读取用户个人信息"""
        return db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
    
    @staticmethod
    def create_user_profile(
        db: Session,
        user_id: int,
        target_job: Optional[str] = None,
        years_experience: Optional[str] = None,
        target_level: Optional[str] = None,
        target_skills: Optional[list[str]] = None,
        weak_topics: Optional[list[str]] = None,
    ) -> UserProfile:
        """创建用户个人信息"""
        profile = UserProfile(
            user_id=user_id,
            target_job=target_job,
            years_experience=years_experience,
            target_level=target_level,
            target_skills=target_skills or [],
            weak_topics=weak_topics or [],
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile
    
    @staticmethod
    def update_user_profile(
        db: Session,
        user_id: int,
        target_job: Optional[str] = None,
        years_experience: Optional[str] = None,
        target_level: Optional[str] = None,
        target_skills: Optional[list[str]] = None,
        weak_topics: Optional[list[str]] = None,
    ) -> Optional[UserProfile]:
        """更新用户个人信息（仅更新非None字段）"""
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        
        if not profile:
            return None
        
        if target_job is not None:
            profile.target_job = target_job
        if years_experience is not None:
            profile.years_experience = years_experience
        if target_level is not None:
            profile.target_level = target_level
        if target_skills is not None:
            profile.target_skills = target_skills
        if weak_topics is not None:
            profile.weak_topics = weak_topics
        
        db.commit()
        db.refresh(profile)
        return profile
    
    @staticmethod
    def delete_user_profile(db: Session, user_id: int) -> bool:
        """删除用户个人信息"""
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        
        if not profile:
            return False
        
        db.delete(profile)
        db.commit()
        return True
    
    @staticmethod
    def get_profile_dict(db: Session, user_id: int) -> dict:
        """读取用户信息转字典（缺失字段使用默认值）"""
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        
        return {
            "target_job": profile.target_job if profile and profile.target_job else "未指定",
            "years_experience": profile.years_experience if profile and profile.years_experience else "未指定",
            "target_level": profile.target_level if profile and profile.target_level else "未指定",
            "target_skills": profile.target_skills if profile and profile.target_skills else [],
            "weak_topics": profile.weak_topics if profile and profile.weak_topics else [],
        }
    
    @staticmethod
    def format_profile_for_injection(profile_dict: dict) -> dict:
        """格式化用户信息用于提示词注入（数组→文本）
        
        转换规则：["Python", "FastAPI"] → "Python、FastAPI"
        """
        target_skills = profile_dict.get("target_skills", [])
        target_skills_str = "、".join(target_skills) if isinstance(target_skills, list) and target_skills else "未指定"
        
        weak_topics = profile_dict.get("weak_topics", [])
        weak_topics_str = "、".join(weak_topics) if isinstance(weak_topics, list) and weak_topics else "未指定"
        
        return {
            "target_job": str(profile_dict.get("target_job", "未指定")),
            "years_experience": str(profile_dict.get("years_experience", "未指定")),
            "target_level": str(profile_dict.get("target_level", "未指定")),
            "target_skills": target_skills_str,
            "weak_topics": weak_topics_str,
        }
