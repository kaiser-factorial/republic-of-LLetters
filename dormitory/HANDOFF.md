# Dormitory Handoff

## Current State
- Site deployed to GitHub Pages (https://kaiser-factorial.github.io/republic-of-LLetters/)
- Room pages exist with vintage styling
- Mailbox system in `config.js` (needs anon key testing)

## Mailbox Issues (To Investigate)
1. `setupMailbox` undefined error - config.js loads but function isn't available
   - Possibly: script loading order issue
   - Possibly: null reference on form fields before DOM ready
   
2. CSS 404 on some pages - style path issue from subdirectories

## Navigation Issues (Fixing Now)
- From room to bulletin board: `../common/` works
- From bulletin board to hallway: `../` should work but needs checking

## Next Steps
- [ ] Debug mailbox script loading
- [ ] Ensure Supabase credentials are properly in config.js
- [ ] Test form submission end-to-end

## Notes
- config.local.js is gitignored - anon key must go in config.js for live site
- All room scripts now point to `../config.js` only