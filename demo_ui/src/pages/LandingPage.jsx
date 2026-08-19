import { Link } from 'react-router-dom'
import Logo from '../components/Logo.jsx'

const LeafIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6 text-brand-600" viewBox="0 0 24 24" fill="currentColor">
    <path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3A4.49 4.49 0 008 20C19 20 22 3 22 3c-1 2-8 2-5 8z" />
  </svg>
)

const SparkleIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-brand-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 3v18" />
    <path d="M3 12h18" />
    <path d="M6 6l12 12" />
    <path d="M6 18L18 6" />
  </svg>
)

const PlayIcon = ({ className = "w-5 h-5" }) => (
  <svg xmlns="http://www.w3.org/2000/svg" className={className} viewBox="0 0 24 24" fill="currentColor">
    <path fillRule="evenodd" d="M4.5 5.653c0-1.426 1.529-2.33 2.779-1.643l11.54 6.348c1.295.712 1.295 2.573 0 3.285L7.28 20.015c-1.25.687-2.779-.217-2.779-1.643V5.653z" clipRule="evenodd" />
  </svg>
)

export default function LandingPage() {
  return (
    <div className="min-h-dvh relative bg-[#FDFDFD] overflow-hidden selection:bg-brand-200 dark:bg-slate-950 dark:text-slate-100">
      
      {/* Premium Generated Background Image */}
      <div 
        className="absolute inset-0 z-0 pointer-events-none" 
        style={{ 
          backgroundImage: "linear-gradient(to bottom, rgba(253, 253, 253, 0.4), rgba(253, 253, 253, 0.9)), url('/bg.png')",
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat'
        }} 
      />

      {/* Floating 3D Elements (CSS approximations) */}
      <div className="absolute top-40 right-20 w-64 h-64 bg-brand-600 rounded-3xl rotate-12 opacity-80 blur-[2px] z-0 animate-fade-in-up shadow-2xl" style={{ animationDelay: '300ms' }} />
      <div className="absolute top-52 right-32 w-48 h-48 bg-white/40 backdrop-blur-xl border border-white/60 rounded-3xl rotate-6 z-10 animate-fade-in-up shadow-xl flex items-center justify-center" style={{ animationDelay: '500ms' }}>
        <div className="flex gap-3 items-end h-24">
          <div className="w-5 h-16 bg-white/70 rounded-full" />
          <div className="w-5 h-20 bg-white/70 rounded-full" />
          <div className="w-5 h-12 bg-white/70 rounded-full" />
        </div>
      </div>

      <div className="absolute top-48 left-20 w-48 h-48 bg-white/40 backdrop-blur-md border border-white/60 rounded-3xl -rotate-12 z-10 animate-fade-in-up shadow-xl flex items-center justify-center opacity-60" style={{ animationDelay: '400ms' }}>
         <span className="text-6xl font-bold text-slate-300">24</span>
      </div>


      <div className="relative z-20 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        
        {/* Navigation Bar */}
        <nav className="flex items-center justify-between px-6 py-4 bg-white/80 backdrop-blur-xl border border-gray-100 rounded-full shadow-[0_8px_30px_rgb(0,0,0,0.04)] animate-fade-in-up">
          <Logo className="w-8 h-8" withText={true} />
          
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600">
            <a href="#" className="hover:text-slate-900 transition-colors">About Project</a>
            <a href="#team" className="hover:text-slate-900 transition-colors">Team Members</a>
            <a href="#" className="hover:text-slate-900 transition-colors">ISO 14001</a>
            <a href="#" className="hover:text-slate-900 transition-colors">Documentation</a>
          </div>
          
          <div className="flex items-center gap-4">
            <Link to="/register" className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 transition-all">
              Get Started
            </Link>
          </div>
        </nav>

        {/* Hero Section */}
        <div className="relative text-center mt-28 mb-24 max-w-4xl mx-auto">
          
          {/* Radial glow to improve text focus against the background */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[120%] h-[150%] bg-[radial-gradient(ellipse_at_center,_rgba(255,255,255,0.9)_0%,_rgba(255,255,255,0.7)_40%,_transparent_70%)] blur-xl -z-10 pointer-events-none" />

          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-white/90 backdrop-blur-sm border border-gray-200/60 shadow-sm mb-8 animate-fade-in-up" style={{ animationDelay: '100ms' }}>
            <SparkleIcon />
            <span className="text-[11px] font-bold text-slate-600 tracking-widest uppercase">Automated ISO 14001 Assistant</span>
          </div>

          {/* Headline */}
          <h1 className="text-6xl md:text-7xl font-extrabold text-slate-900 tracking-tighter leading-[1.1] mb-6 animate-fade-in-up drop-shadow-sm" style={{ animationDelay: '200ms' }}>
            AI-Powered <br />Compliance Assistant
          </h1>
          
          {/* Subtitle */}
          <p className="text-lg md:text-xl font-medium text-slate-600 mb-10 max-w-3xl mx-auto animate-fade-in-up drop-shadow-sm" style={{ animationDelay: '300ms' }}>
            Automated ISO 14001 gap analysis and actionable sustainability recommendations.
          </p>
          
          {/* Action Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 animate-fade-in-up" style={{ animationDelay: '400ms' }}>
            <Link to="/login" className="inline-flex items-center justify-center rounded-2xl bg-white/80 backdrop-blur-md px-8 py-4 text-sm font-semibold text-slate-900 shadow-sm ring-1 ring-inset ring-gray-200/50 hover:bg-white transition-all hover:scale-105 active:scale-95">
              <PlayIcon className="mr-2 h-5 w-5 text-slate-700" />
              Watch Demo
            </Link>
          </div>
        </div>

﻿        {/* Dashboard Preview Wrapper */}
        <div className="relative mx-auto max-w-5xl rounded-t-3xl border border-gray-200/60 bg-white/50 backdrop-blur-sm p-4 shadow-2xl animate-fade-in-up h-[600px] overflow-hidden" style={{ animationDelay: '600ms' }}>
          
          {/* Window Controls */}
          <div className="flex items-center gap-2 mb-4 pl-2">
            <div className="w-3 h-3 rounded-full bg-red-400" />
            <div className="w-3 h-3 rounded-full bg-amber-400" />
            <div className="w-3 h-3 rounded-full bg-emerald-400" />
            <div className="mx-auto bg-gray-100 rounded-md px-3 py-1 text-[10px] font-medium text-slate-400 flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              VerdeAI ISO 14001 Dashboard
            </div>
          </div>

          {/* Faded Dashboard Mockup content */}
          <div className="flex gap-4 h-full opacity-90">
            {/* Sidebar Mock */}
            <div className="w-56 bg-white rounded-xl border border-gray-100 p-4 flex flex-col gap-3 shadow-sm">
               <div className="flex items-center gap-2 mb-6 border-b border-gray-100 pb-4">
                 <Logo className="w-6 h-6" withText={true} textClassName="text-slate-900 text-sm font-bold tracking-tight" />
               </div>
               
               {/* Nav Links Mock */}
               <div className="h-10 bg-brand-50 rounded-lg w-full flex items-center px-3 gap-3 text-brand-700">
                 <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                   <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
                 </svg>
                 <span className="text-xs font-semibold">Dashboard</span>
               </div>
               <div className="h-10 bg-transparent rounded-lg w-full flex items-center px-3 gap-3 text-slate-400">
                 <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                   <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                 </svg>
                 <span className="text-xs font-medium">Documents</span>
               </div>
               <div className="h-10 bg-transparent rounded-lg w-full flex items-center px-3 gap-3 text-slate-400">
                 <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                   <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                 </svg>
                 <span className="text-xs font-medium">Org Profile</span>
               </div>
               <div className="h-10 bg-transparent rounded-lg w-full flex items-center px-3 gap-3 text-slate-400">
                 <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                   <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                 </svg>
                 <span className="text-xs font-medium">Gap Analysis</span>
               </div>
            </div>
            
            {/* Main Area Mock */}
            <div className="flex-1 flex flex-col gap-6">
              {/* Topbar */}
              <div className="h-14 bg-white/60 backdrop-blur-md rounded-xl flex items-center justify-between px-6 border border-gray-100 shadow-sm">
                 <div className="flex items-center gap-3">
                   <div className="w-8 h-8 rounded-lg bg-brand-100 text-brand-600 flex items-center justify-center">
                     <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                       <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                     </svg>
                   </div>
                   <span className="text-sm font-semibold text-slate-800">Acme Corp Compliance Overview</span>
                 </div>
                 <div className="flex gap-3 items-center">
                   <div className="w-8 h-8 rounded-full bg-slate-100" />
                   <div className="w-8 h-8 rounded-full bg-brand-500 border-2 border-white shadow-sm" />
                 </div>
              </div>
              
              {/* Content Grid */}
              <div className="grid grid-cols-3 gap-4">
                {/* Score Card */}
                <div className="col-span-1 h-32 bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex flex-col justify-between relative overflow-hidden">
                   <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Overall ISO 14001 Score</span>
                   <div className="flex items-end gap-2">
                     <span className="text-4xl font-bold text-slate-900">72%</span>
                     <span className="text-sm font-medium text-emerald-500 mb-1">+4% this month</span>
                   </div>
                   <div className="absolute bottom-0 left-0 w-full h-1 bg-gray-100">
                     <div className="h-full bg-brand-500 w-[72%]" />
                   </div>
                </div>

                {/* Clauses Met Card */}
                <div className="col-span-1 h-32 bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex flex-col justify-between">
                   <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Clauses Met</span>
                   <div className="flex items-end gap-2">
                     <span className="text-4xl font-bold text-slate-900">28</span>
                     <span className="text-sm font-medium text-slate-400 mb-1">/ 42</span>
                   </div>
                </div>

                {/* Open Gaps Card */}
                <div className="col-span-1 h-32 bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex flex-col justify-between">
                   <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Actionable Gaps</span>
                   <div className="flex items-end gap-2">
                     <span className="text-4xl font-bold text-amber-500">14</span>
                     <span className="text-sm font-medium text-slate-400 mb-1">open items</span>
                   </div>
                </div>
              </div>

              {/* Large Section */}
              <div className="h-48 bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex gap-6">
                <div className="flex-1 flex flex-col gap-4">
                  <span className="text-sm font-bold text-slate-800">Recent AI Analysis Recommendations</span>
                  <div className="w-full h-8 bg-amber-50/50 border border-amber-100 rounded-lg flex items-center px-3 gap-2">
                    <div className="w-2 h-2 rounded-full bg-amber-400" />
                    <div className="w-3/4 h-2 bg-amber-200/50 rounded" />
                  </div>
                  <div className="w-full h-8 bg-red-50/50 border border-red-100 rounded-lg flex items-center px-3 gap-2">
                    <div className="w-2 h-2 rounded-full bg-red-400" />
                    <div className="w-1/2 h-2 bg-red-200/50 rounded" />
                  </div>
                  <div className="w-full h-8 bg-emerald-50/50 border border-emerald-100 rounded-lg flex items-center px-3 gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-400" />
                    <div className="w-2/3 h-2 bg-emerald-200/50 rounded" />
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Fade out gradient at bottom */}
          <div className="absolute bottom-0 left-0 right-0 h-40 bg-gradient-to-t from-[#FDFDFD] to-transparent" />
        </div>

      </div>

      {/* Our Team Section */}
      <section id="team" className="py-24 bg-white border-t border-gray-100 mt-20 relative z-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16 animate-fade-in-up">
            <h2 className="text-4xl md:text-5xl font-extrabold text-slate-900 tracking-tight">Our Team</h2>
          </div>

          <div className="flex flex-wrap justify-center gap-10 md:gap-16">
            {[
              { name: 'THARUSHA', id: '235543L', img: 'tharusha.jpg', delay: '100ms' },
              { name: 'ARRATHIKASARMA', id: '235506D', img: 'arrathikasarma.jpg', delay: '200ms' },
              { name: 'SAMA', id: '235519U', img: 'sama.jpg', delay: '300ms' },
              { name: 'RANSIKA', id: '235532D', img: 'ransika.jpg', delay: '400ms' },
              { name: 'SAJEETHAN', id: '215555G', img: 'sajeethan.jpg', delay: '500ms' },
            ].map((member) => (
              <div key={member.id} className="flex flex-col items-center animate-fade-in-up" style={{ animationDelay: member.delay, animationFillMode: 'both' }}>
                <div className="w-32 h-32 md:w-40 md:h-40 rounded-full overflow-hidden bg-slate-100 shadow-lg ring-4 ring-white mb-5 transition-transform duration-300 hover:scale-105">
                  <img
                    src={`/team/${member.img}`}
                    alt={member.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.target.onerror = null;
                      e.target.src = `https://ui-avatars.com/api/?name=${member.name}&background=f1f5f9&color=64748b&size=200`;
                    }}
                  />
                </div>
                <h3 className="text-lg font-bold text-slate-900 tracking-wide">{member.name}</h3>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Our Supervisors Section */}
      <section className="py-20 bg-[#FDFDFD] relative z-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16 animate-fade-in-up">
            <h2 className="text-4xl md:text-5xl font-extrabold text-slate-900 tracking-tight">Our Supervisors</h2>
          </div>

          <div className="flex flex-wrap justify-center gap-10 md:gap-16">
            {[
              { 
                name: 'Prof. A.S. Karunananda', 
                img: 'karunananda.jpg', 
                roles: ['Senior Professor', 'Department of Computational Mathematics', 'Faculty of Information Technology'],
                delay: '100ms' 
              },
              { 
                name: 'Mr. Lakshitha Attanayaka', 
                img: 'lakshitha.jpg', 
                roles: ['Senior Tech Lead', 'Mitra Innovation'],
                delay: '200ms' 
              },
              { 
                name: 'Mr. Chathuraka Mallawa Arachchi', 
                img: 'chathuraka.jpg', 
                roles: ['Senior Tech Lead', 'Mitra Innovation'],
                delay: '300ms' 
              },
            ].map((supervisor) => (
              <div key={supervisor.name} className="flex flex-col items-center animate-fade-in-up text-center max-w-[300px]" style={{ animationDelay: supervisor.delay, animationFillMode: 'both' }}>
                <div className="w-40 h-40 md:w-48 md:h-48 rounded-full overflow-hidden bg-slate-100 shadow-lg ring-4 ring-white mb-6 transition-transform duration-300 hover:scale-105">
                  <img
                    src={`/team/${supervisor.img}`}
                    alt={supervisor.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.target.onerror = null;
                      e.target.src = `https://ui-avatars.com/api/?name=${supervisor.name}&background=f1f5f9&color=64748b&size=200`;
                    }}
                  />
                </div>
                <h3 className="text-lg font-bold text-slate-900 tracking-wide mb-3">{supervisor.name}</h3>
                {supervisor.roles.map((role, i) => (
                  <p key={i} className="text-sm font-medium text-slate-500 leading-tight mb-1">{role}</p>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

