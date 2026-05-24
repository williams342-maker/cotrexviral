import React from 'react';
import CVLandingPage from '../../components/cv/CVLandingPage';
import { TIKTOK, VIRAL_IDEAS, INSTAGRAM, SHORT_FORM, AUTOMATION } from './content';

export const TikTokGenerator = () => <CVLandingPage {...TIKTOK} />;
export const ViralIdeas = () => <CVLandingPage {...VIRAL_IDEAS} />;
export const InstagramCaption = () => <CVLandingPage {...INSTAGRAM} />;
export const ShortFormVideo = () => <CVLandingPage {...SHORT_FORM} />;
export const ContentAutomation = () => <CVLandingPage {...AUTOMATION} />;
