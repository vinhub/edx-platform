$(function () {
    'use strict';    // create an instance of the Application object;
    // note, that different instances of Application may
    // represent different users
    var config = {
        apiKey: 'f3b6a1b0-8e53-4ef1-91a4-8cf35fcc2bb1', // SDK
        apiKeyCC: '9c967f6b-a846-4df2-b43d-5167e47d81e1' // SDK+UI
    };
    var Application;
    var client;
    Skype.initialize({apiKey: config.apiKey}, function (api) {

        Application = new api.application();
        //Make sign in table appear
        $(".menu #sign-in").click();
        // whenever client.state changes, display its value
        Application.signInManager.state.changed(function (state) {
           console.log(state);
        });
    }, function (err) {
        console.log(err);
        alert('Cannot load the SDK.');
    });

    // whenever state changes, display its value
    Application.signInManager.state.changed(function (state) {
        console.log(state);
    });
    $('.signin').click(function () {
        // when the user clicks on the "Sign In" button    $('#signin').click(function () {
        // start signing in
        Application.signInManager.signIn({
            username: 'O365Admin@introptest.onmicrosoft.com',
            password: 'Pwd&0011'
        }).then(
            //onSuccess callback
            function () {
                // when the sign in operation succeeds display the user name
                alert('Signed in as ' + Application.personsAndGroupsManager.mePerson.displayName());
            },
            //onFailure callback
            function (error) {
                // if something goes wrong in either of the steps above,
                // display the error message
                alert(error || 'Cannot sign in');
            });
    });

    // when the user clicks on the "Sign Out" button
    $('#signout').click(function () {
        // start signing out
        Application.signInManager.signOut()
            .then(
                //onSuccess callback
                function () {
                    // and report the success
                    alert('Signed out');
                },
                //onFailure callback
                function (error) {
                    // or a failure
                    alert(error || 'Cannot sign in');
                });
    });
});