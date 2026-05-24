import React from 'react';
import { useLocation, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2, ShieldAlert } from 'lucide-react';

const ProtectedRoute = ({ children, admin }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F6F4ED]">
        <Loader2 className="animate-spin text-[#1B7BFF]" size={28} />
      </div>
    );
  }

  const effectiveUser = user || location.state?.user;
  if (!effectiveUser) return <Navigate to="/" replace />;

  if (admin && !effectiveUser.is_admin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F6F4ED] p-6">
        <div className="bg-white rounded-3xl p-8 max-w-md border border-rose-200 text-center">
          <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-3">
            <ShieldAlert size={20} />
          </div>
          <h2 className="text-xl font-semibold mb-2">Admin access required</h2>
          <p className="text-[14px] text-neutral-600 mb-4">You don't have permission to view this page.</p>
          <a href="/dashboard" className="inline-flex items-center gap-2 bg-[#1B7BFF] hover:bg-[#1668e0] text-white text-[13px] font-medium px-5 h-10 rounded-xl">
            Go to dashboard
          </a>
        </div>
      </div>
    );
  }
  return children;
};

export default ProtectedRoute;
