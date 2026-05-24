import React from 'react';
import { useLocation, Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2 } from 'lucide-react';

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F6F4ED]">
        <Loader2 className="animate-spin text-[#1B7BFF]" size={28} />
      </div>
    );
  }

  // Allow if user is set via location.state (just-logged-in flow)
  if (!user && !location.state?.user) {
    return <Navigate to="/" replace />;
  }
  return children;
};

export default ProtectedRoute;
