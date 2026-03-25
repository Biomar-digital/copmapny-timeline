import { timelineEvents } from './data/timelineData'
import TimelineEvent from './components/TimelineEvent'
import styles from './App.module.css'

export default function App() {
  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <h1 className={styles.heading}>Our Journey</h1>
        <p className={styles.subheading}>
          A look at the milestones that shaped who we are today
        </p>
      </header>

      <main className={styles.main}>
        <div className={styles.timeline}>
          <div className={styles.line} />
          {timelineEvents.map((event, index) => (
            <TimelineEvent key={event.id} event={event} index={index} />
          ))}
        </div>
      </main>

      <footer className={styles.footer}>
        <p>© {new Date().getFullYear()} Company Timeline. All rights reserved.</p>
      </footer>
    </div>
  )
}
