import io, wave, uuid
from collections.abc import AsyncIterator
import pytest
from sqlalchemy import select
from app.db import session as db_session
from app.models.meetings import Meeting, MeetingAudioChunk
from app.models.agent import AgentJob
from app.core.enums import MeetingStatus, AgentJobKind, AgentJobStatus
from app.infra.storage import save_file
from tests.integration.test_audio_ws import account_meeting
pytestmark=[pytest.mark.db,pytest.mark.anyio]
@pytest.fixture
async def app_db(migrated_db_url,monkeypatch,clear_db_caches,tmp_path)->AsyncIterator[None]:
 monkeypatch.setenv('DATABASE_URL',migrated_db_url);monkeypatch.setenv('STORAGE_DIR',str(tmp_path));yield;await db_session.get_engine().dispose()
def wav():
 out=io.BytesIO()
 with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0'*3200)
 return out.getvalue()
async def test_review_submit_poll_uses_persisted_job_and_temp_audio(client,app_db,monkeypatch):
 token,meeting=account_meeting(client);headers={'Authorization':f'Bearer {token}'}
 async with db_session.get_sessionmaker()() as s:
  row=await s.get(Meeting,meeting);row.status=MeetingStatus.COMPLETED
  job=AgentJob(club_id=row.club_id,kind=AgentJobKind.MEETING_STT,status=AgentJobStatus.SUCCEEDED);s.add(job);await s.flush();key=save_file(row.club_id,'audio.wav',wav());s.add(MeetingAudioChunk(meeting_id=meeting,seq=1,start_ms=0,end_ms=100,storage_key=key,sha256='a'*64,mime_type='audio/wav',size=len(wav()),job_id=job.id));await s.commit()
 class Fake:
  def __init__(self,*a,**k): pass
  async def submit(self,path): assert path.exists(); return 'provider-1'
  async def result(self,job_id,duration_ms): assert job_id=='provider-1'; return [{'start_ms':0,'end_ms':100,'speaker_label':'SPEAKER_00'}]
 monkeypatch.setattr('app.routers.meetings.PyannoteDiarization',Fake)
 assert client.post(f'/api/v1/meetings/{meeting}/review',headers=headers).status_code==202
 submitted=client.post(f'/api/v1/meetings/{meeting}/review/submit',headers=headers);assert submitted.status_code==202 and submitted.json()['data']['status']=='PROCESSING'
 polled=client.post(f'/api/v1/meetings/{meeting}/review/poll',headers=headers);assert polled.status_code==200 and polled.json()['data']['status']=='NEEDS_REVIEW'
