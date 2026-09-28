"""站点配置 API"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Site
from app.schemas import SiteCreate, SiteRead, SiteUpdate

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.get("", response_model=list[SiteRead])
def list_sites(session: Session = Depends(get_session)):
    return session.exec(select(Site).order_by(Site.id.desc())).all()


@router.post("", response_model=SiteRead)
def create_site(payload: SiteCreate, session: Session = Depends(get_session)):
    # 检查 host 唯一
    exist = session.exec(select(Site).where(Site.host == payload.host)).first()
    if exist:
        raise HTTPException(409, f"已存在 host={payload.host} 的站点")
    site = Site(**payload.model_dump())
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


@router.get("/{site_id}", response_model=SiteRead)
def get_site(site_id: int, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(404, "site 不存在")
    return site


@router.patch("/{site_id}", response_model=SiteRead)
def update_site(site_id: int, payload: SiteUpdate, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(404, "site 不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(site, k, v)
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


@router.delete("/{site_id}")
def delete_site(site_id: int, session: Session = Depends(get_session)):
    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(404, "site 不存在")
    session.delete(site)
    session.commit()
    return {"ok": True}


@router.post("/{site_id}/probe")
def probe_site(site_id: int, session: Session = Depends(get_session)):
    """测试站点连通性：用 requests 抓首页，返回 status + title"""
    import httpx

    site = session.get(Site, site_id)
    if not site:
        raise HTTPException(404, "site 不存在")
    ua = site.user_agent or "Mozilla/5.0"
    headers = {"User-Agent": ua}
    try:
        r = httpx.get(site.base_url, headers=headers, timeout=15.0, follow_redirects=True)
        title = ""
        if r.status_code == 200:
            import re

            m = re.search(r"<title>([^<]+)</title>", r.text)
            if m:
                title = m.group(1).strip()
        return {
            "ok": r.status_code == 200,
            "status": r.status_code,
            "title": title,
            "url": str(r.url),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
