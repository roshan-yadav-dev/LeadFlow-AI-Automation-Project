import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * LoginPage has been decommissioned.
 * Users directly authenticate and are routed to the main control dashboard.
 */
export const LoginPage: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    navigate('/', { replace: true });
  }, [navigate]);

  return null;
};

export default LoginPage;

