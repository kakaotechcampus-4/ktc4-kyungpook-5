import { Link } from 'react-router-dom'
import { Tori } from '@/shared/ui/Tori'
import './service-home.css'

type ServiceHomePageProps = { primaryHref: string; primaryLabel: string }

function Arrow({ down = false }: { down?: boolean }) {
  return (
    <svg
      aria-hidden="true"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={down ? 'sh-arrow-down' : undefined}
    >
      <path d="M5 12h14m-6-6 6 6-6 6" />
    </svg>
  )
}

export default function ServiceHomePage({ primaryHref, primaryLabel }: ServiceHomePageProps) {
  return (
    <div className="service-home">
      <a className="sh-skip" href="#top">
        본문으로 건너뛰기
      </a>
      <header className="sh-header">
        <a className="sh-brand" href="#top" aria-label="운영해 처음으로">
          <Tori size={40} />
          <span>운영해</span>
        </a>
        <nav aria-label="주요 메뉴">
          <a href="#how">운영해 알아보기</a>
          <Link to={primaryHref}>{primaryHref === '/login' ? '로그인' : '서비스 열기'}</Link>
        </nav>
      </header>
      <main id="top" tabIndex={-1}>
        <section className="sh-hero">
          <div className="sh-hero-copy">
            <h1>
              팀의 운영을,
              <br />
              함께 기억해요.
            </h1>
            <p>
              회의에서 나눈 이야기부터 흩어진 자료까지.
              <br className="sh-desktop-break" /> 동아리 운영에 필요한 순간, 토리에게 물어보세요.
            </p>
            <div className="sh-actions">
              <Link className="sh-primary" to={primaryHref}>
                {primaryLabel}
                <Arrow />
              </Link>
              <a className="sh-secondary" href="#how">
                어떻게 쓰나요? <Arrow down />
              </a>
            </div>
          </div>
          <div className="sh-visual" aria-label="토리와 자료를 확인하는 가상 예시" data-ui>
            <div className="sh-visual-top">
              <div className="sh-window-title">
                <Tori size={36} />
                <span>
                  <strong>토리와 대화</strong>
                  <small>운영해 팀 비서</small>
                </span>
              </div>
              <span className="sh-example">가상 예시</span>
            </div>
            <div className="sh-conversation">
              <div className="sh-user">지난 워크숍은 어디에서 했어?</div>
              <div className="sh-answer">
                <Tori size={32} />
                <div>
                  <strong>토리</strong>
                  <p>지난 워크숍은 교내 세미나실에서 진행했어요. 회고 자료에서 확인했어요.</p>
                  <details className="sh-source">
                    <summary>
                      <span>
                        <b>워크숍 회고.pdf</b>
                        <small>예시 근거 펼쳐보기</small>
                      </span>
                      <Arrow down />
                    </summary>
                    <blockquote>
                      장소: 교내 세미나실
                      <br />
                      진행 내용: 신입 부원 소개와 팀별 활동
                    </blockquote>
                  </details>
                </div>
              </div>
            </div>
            <p className="sh-visual-note">답변과 함께 근거를 확인해 보세요.</p>
          </div>
        </section>
        <section id="how" className="sh-how">
          <div className="sh-section-heading">
            <h2>
              바쁜 운영 사이,
              <br />
              다음 일을 챙겨요.
            </h2>
            <p>
              토리와 대화하며 팀의 기록을 찾고,
              <br />
              회의 뒤에는 다음 일을 차근차근 확인해요.
            </p>
          </div>
          <div className="sh-features">
            <article className="sh-feature">
              <h3>
                자료를 찾고,
                <br />
                근거까지 확인해요.
              </h3>
              <p>
                파일 이름이 떠오르지 않아도 궁금한 내용을 물어보고, 답변의 근거와 원본 자료를 확인할
                수 있어요.
              </p>
              <figure className="sh-record-preview" data-ui>
                <figcaption>
                  <strong>자료함</strong>
                  <span>가상 예시</span>
                </figcaption>
                <p className="sh-preview-query">워크숍 준비 자료</p>
                <div className="sh-record-row">
                  <strong>워크숍 회고.pdf</strong>
                  <span>장소 · 진행 내용</span>
                </div>
                <div className="sh-record-row">
                  <strong>워크숍 준비 목록.pdf</strong>
                  <span>준비물 · 역할</span>
                </div>
              </figure>
            </article>
            <article className="sh-feature">
              <h3>
                회의가 끝나면,
                <br />
                다음 일을 확인해요.
              </h3>
              <p>
                회의 내용을 살펴보고 일정과 할 일 후보의 내용, 시간, 담당자를 확인한 뒤 저장할 수
                있어요.
              </p>
              <div className="sh-followups">
                <figure className="sh-followup-preview" data-ui>
                  <figcaption>
                    <strong>일정 후보</strong>
                    <span>가상 예시</span>
                  </figcaption>
                  <p>워크숍 준비 회의</p>
                  <span>일정 시간과 내용을 확인한 뒤 저장</span>
                </figure>
                <figure className="sh-followup-preview" data-ui>
                  <figcaption>
                    <strong>할 일 후보</strong>
                    <span>가상 예시</span>
                  </figcaption>
                  <p>준비물 목록 정리</p>
                  <span>담당자와 기한을 확인한 뒤 저장</span>
                </figure>
              </div>
            </article>
          </div>
        </section>
        <section className="sh-closing">
          <div>
            <h2>
              우리 팀의 다음 일을
              <br />
              토리와 시작해요.
            </h2>
            <p>자료를 찾는 질문부터, 작은 일 하나씩.</p>
          </div>
          <Link className="sh-primary sh-primary-light" to={primaryHref}>
            {primaryLabel}
            <Arrow />
          </Link>
        </section>
      </main>
      <footer className="sh-footer">
        <div className="sh-brand">
          <Tori size={34} />
          <span>운영해</span>
        </div>
        <p>팀의 운영을 함께 기억하는 비서</p>
        <Link to={primaryHref}>{primaryHref === '/login' ? '로그인' : '서비스 열기'}</Link>
      </footer>
    </div>
  )
}
