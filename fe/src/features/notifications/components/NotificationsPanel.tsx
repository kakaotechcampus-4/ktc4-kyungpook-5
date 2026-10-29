import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { notificationServer, type PushServerAdapter } from '../api'
import { notificationErrorMessage, useSystemNotifications } from '../hooks'

interface NotificationsPanelProps {
  server?: PushServerAdapter
}

export function NotificationsPanel({ server = notificationServer }: NotificationsPanelProps) {
  const notifications = useSystemNotifications(server)
  const allowed = notifications.permission === 'granted'
  const unsupported = notifications.permission === 'unsupported'
  const pushReady = notifications.configuration.data?.publicKey

  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[14px] font-bold text-ink">이 기기 알림</h2>
        <Chip tone={allowed ? 'done' : 'pending'} size="sm">
          {unsupported
            ? '지원 환경 필요'
            : allowed
              ? '권한 허용'
              : notifications.permission === 'denied'
                ? '권한 차단'
                : '권한 확인 전'}
        </Chip>
      </div>
      <p className="mb-3 text-[12px] leading-5 text-ink2">
        Chrome의 설치 메뉴로 앱을 설치할 수 있어요. 알림은 아래 버튼을 눌러 별도로 허용해 주세요.
      </p>
      {unsupported && (
        <p className="mb-3 text-[12px] text-failed">
          HTTPS 또는 localhost의 알림 지원 브라우저에서 열어 주세요.
        </p>
      )}
      {notifications.permission === 'denied' && (
        <p className="mb-3 text-[12px] text-ink2">
          브라우저의 사이트 설정에서 알림을 허용한 뒤 이 화면으로 돌아와 주세요.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={
            unsupported || allowed || notifications.permission === 'denied' || notifications.busy
          }
          onClick={() => void notifications.requestPermission()}
        >
          알림 허용
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={!allowed || notifications.busy}
          onClick={() => void notifications.checkLocally()}
        >
          이 기기에서 알림 확인
        </Button>
      </div>

      <div className="mt-4 border-t border-line pt-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="text-[12px] font-bold text-ink">서버 Push</h3>
          <Chip size="sm" tone={notifications.registered ? 'done' : 'neutral'}>
            {!server
              ? '서버 계약 미연결'
              : notifications.registered
                ? '이 기기 등록 완료'
                : notifications.configuration.error
                  ? '서버 연결 확인 필요'
                  : '서버 등록 확인 전'}
          </Chip>
        </div>
        <p className="mb-3 text-[12px] leading-5 text-ink2">
          {server
            ? '구독은 현재 로그인 계정에 등록해요. 서버 Push 접수와 실제 기기 수신은 별도로 확인해 주세요.'
            : '서버 Push 등록과 예약 발송은 아직 연결되지 않았어요. 위 알림 확인은 이 기기에서만 실행하는 로컬 검사예요.'}
        </p>
        <div className="flex flex-wrap gap-2">
          {notifications.configuration.error && (
            <Button
              size="sm"
              variant="ghost"
              disabled={notifications.configuration.isFetching}
              onClick={notifications.retryServer}
            >
              서버 연결 다시 확인
            </Button>
          )}
          <Button
            size="sm"
            variant="secondary"
            disabled={
              !server ||
              !pushReady ||
              !allowed ||
              !notifications.webPushSupported ||
              notifications.busy
            }
            onClick={notifications.subscribe}
          >
            이 기기 Push 등록
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={!server || !notifications.registered || notifications.busy}
            onClick={notifications.testPush}
          >
            서버 테스트 Push
          </Button>
          {notifications.registered && (
            <Button
              size="sm"
              variant="ghost"
              disabled={notifications.busy}
              onClick={notifications.unsubscribe}
            >
              구독 해제
            </Button>
          )}
        </div>
        {server && notifications.configuration.data && !pushReady && (
          <p className="mt-2 text-[12px] text-ink2">서버가 Push 발송을 준비 중이에요.</p>
        )}
      </div>
      <p className="mt-3 text-[11px] leading-5 text-mute">
        예약은 후보의 내용·시간·담당자와 수신자를 확인한 뒤 서버에 저장해야 해요. 이 버튼으로 예약이
        생성되지는 않아요.
      </p>
      {notifications.notice && (
        <p role="status" className="mt-3 text-[12px] leading-5 text-ink2">
          {notifications.notice}
        </p>
      )}
      {!!notifications.error && (
        <p role="alert" className="mt-3 text-[12px] leading-5 text-failed">
          {notificationErrorMessage(notifications.error)}
        </p>
      )}
    </Card>
  )
}
